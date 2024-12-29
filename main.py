import asyncio
import aiohttp
from bilibili_api import video, Credential, sync, HEADERS, user
import httpx
import os
from tqdm import tqdm
from ffmpy import FFmpeg
import subprocess
from dotenv import load_dotenv

load_dotenv()
SESSDATA = os.getenv("SESSDATA")
BILI_JCT = os.getenv("BILI_JCT")
BUVID3 = os.getenv("BUVID3")
PROCESSED_ID_FILE = os.getenv("PROCESSED_ID_FILE")

credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
if sync(credential.check_refresh()):
    sync(credential.refresh())

def timestamp_to_time(timestamp):
    # convert timestamp (seconds) to time (HH:MM:SS)
    timestamp = int(timestamp)
    hours = timestamp // 3600
    minutes = (timestamp % 3600) // 60
    seconds = timestamp % 60
    return f"{hours:02d}_{minutes:02d}_{seconds:02d}"

async def download_url(url: str, out: str, info: str):
    print(f"开始下载 {info}")
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        print(f"开始请求")
        async with session.get(url) as resp:
            print(f"获得响应，状态码: {resp.status}")
            length = resp.headers.get('Content-Length')
            print(f"Content-Length: {length}")

            with open(out, 'wb') as f:
                process = 0
                async for chunk in resp.content.iter_chunked(1024):
                    if not chunk:
                        break

                    process += len(chunk)
                    print(f'\r下载 {info} {process} / {length}', end='', flush=True)
                    f.write(chunk)
        print(f"\n{info}下载完成")

def get_time_slots(subtitle):
    slots = []
    flag_music = ['♪' in section['content'] for section in subtitle]
    flag_filtered = [flag_music[i] or flag_music[i + 1] or flag_music[i + 2] for i in range(len(flag_music) - 2)]
    for i, flag in enumerate(flag_filtered):
        if flag and (i == 0 or not flag_filtered[i - 1]):
            start_section = subtitle[i]
            start_timestamp = start_section['start_timestamp']
            slots.append([start_timestamp])
        elif not flag and i > 0 and flag_filtered[i - 1] or i == len(flag_filtered) - 1:
            if len(slots) == 0:
                continue
            end_section = subtitle[i + 2]
            end_timestamp = end_section['end_timestamp']
            slots[-1].append(end_timestamp)

    # filter out slots that are too short (less than 2 minute)
    slots = [slot for slot in slots if slot[1] - slot[0] > 120]

    return slots

def load_processed_bvids(filename=PROCESSED_ID_FILE):
    try:
        with open(filename, 'r') as file:
            return set(file.read().splitlines())
    except FileNotFoundError:
        return set()

async def fetch_bvids(credential=credential):
    target_user_uid = 1548358039
    u = user.User(uid=target_user_uid, credential=credential)
    list1 = await u.get_videos(keyword="宣小纸")
    list1 = list1['list']['vlist']
    # print(list1['list']['vlist'])
    bvid_list = [
        v['bvid'] for v in list1 if "直播录播" in v['title']
    ]

    processed_bvids = load_processed_bvids()

    for bvid in bvid_list:
        if bvid not in processed_bvids:
            yield bvid

async def download_and_clip_video(
        v: video.Video,
        page_index, 
        time_slots, 
        folder="videos"
        ):
    if not os.path.exists(folder):
        os.makedirs(folder)
    temp_folder = "temp"
    if not os.path.exists(temp_folder):
        os.makedirs(temp_folder)
    if not time_slots:
        return
    download_url_data = await v.get_download_url(page_index=page_index)
    # 解析视频下载信息
    detecter = video.VideoDownloadURLDataDetecter(data=download_url_data)
    streams = detecter.detect_best_streams()
    # 有 MP4 流 / FLV 流两种可能
    temp_full_filename = f"{temp_folder}//temp.mp4"
    if detecter.check_flv_stream() == True:
        # FLV 流下载
        flv_filename = f"{temp_folder}//flv_temp.flv"
        await download_url(streams[0].url, flv_filename, "FLV 音视频流")
        # 转换文件格式
        # os.system(f'{FFMPEG_PATH} -i flv_temp.flv video.mp4')
        ff = FFmpeg(
            global_options="-y",
            inputs={flv_filename: None},
            outputs={temp_full_filename: '-vcodec copy -acodec copy -loglevel error'}
        )
        ff.run()
        # 删除临时文件
        # os.remove(flv_filename)
    else:
        # MP4 流下载
        audio_filename = f"{temp_folder}//audio_temp.m4s"
        video_filename = f"{temp_folder}//video_temp.m4s"
        await asyncio.gather(
            download_url(streams[0].url, video_filename, "视频流"),
            download_url(streams[1].url, audio_filename, "音频流")
        )
        # 音频转为mp3
        # os.system(f'{FFMPEG_PATH} -i audio_temp.m4s audio.mp3')
        # 混流
        # os.system(f'{FFMPEG_PATH} -i video_temp.m4s -i audio_temp.m4s -vcodec copy -acodec copy video.mp4')
        ff = FFmpeg(
            global_options="-y",
            inputs={video_filename: None, audio_filename: None},
            outputs={temp_full_filename: '-vcodec copy -acodec copy -loglevel error'}
        )
        ff.run()
        # 删除临时文件
        # os.remove(audio_filename)
        # os.remove(video_filename)
    # clip the video into slots
    info = await v.get_info()
    title = info['title']
    # 从title中提取关键词，“宣小纸”和0-9，其他全部删除
    title = ''.join([c for c in title if c in "宣小纸0123456789"])
    for i, slot in enumerate(time_slots):
        slot_filename = f"{folder}//{title}_{page_index}_{timestamp_to_time(slot[0])}-{timestamp_to_time(slot[1])}.mp4"
        # ff = FFmpeg(
        #     global_options="-y",
        #     inputs={temp_full_filename: None},
        #     outputs={slot_filename: f'-ss {slot[0]} -to {slot[1]}'}
        # )
        # ff.run()
        cmd = [
            "ffmpeg",
            "-i", temp_full_filename,
            "-c", "copy",
            "-ss", str(slot[0]),
            "-t", str(slot[1]),
            "-q:v", "0",
            "-loglevel", "error",
            slot_filename,
            "-y",
        ]
        subprocess.run(cmd)



async def process_video(bvid, credential=credential):
    print(f"processing video {bvid}")
    v = video.Video(bvid=bvid, credential=credential)

    info = await v.get_info()
    keys_to_extract = [
        'videos',
        'title',
    ]
    info = {key: info[key] for key in keys_to_extract}
    print(info)
    for page_index in range(info['videos']):
        summary = await v.get_ai_conclusion(page_index=page_index)
        print(summary)
        subtitle = summary['model_result']['subtitle']
        assert len(subtitle) == 1
        subtitle = subtitle[0]['part_subtitle']
        # print(subtitle)
        time_slots = get_time_slots(subtitle)
        print(f"title: {info['title']}, video: {page_index}")
        for slot in time_slots:
            print(f"{timestamp_to_time(slot[0])} - {timestamp_to_time(slot[1])}")

        # download the videos and clip into slots
        await download_and_clip_video(v, page_index, time_slots, folder="clips")



async def main():
    async for bvid in fetch_bvids():
        await process_video(bvid)
        with open(PROCESSED_ID_FILE, 'a') as file:
            file.write(f"{bvid}\n")
            print(f"{bvid} processed and cliped")

if __name__ == "__main__":
    asyncio.run(main())