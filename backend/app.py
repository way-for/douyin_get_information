from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from curl_cffi import requests as curl_requests
import re
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = BASE_DIR
_parse_cache = {}

app = FastAPI(
    title="抖音作品解析API",
    description="抖音视频/音频/文案/图片提取工具",
    version="1.0.0"
)

# 挂载静态文件目录到 /assets 路由
app.mount("/assets", StaticFiles(directory=os.path.join(BASE_DIR, "assets")), name="assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_cookie():
    """获取Cookie，优先从EXE同目录cookie.txt读取，否则使用内置默认值"""
    # EXE同目录下优先读取（方便用户自定义）
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        external_cookie = os.path.join(exe_dir, 'cookie.txt')
        if os.path.exists(external_cookie):
            try:
                with open(external_cookie, 'r', encoding='utf-8') as f:
                    cookie = f.read().strip()
                if cookie:
                    return cookie
            except:
                pass
        # 使用打包在EXE内的cookie.txt（内置Cookie）
        built_in = os.path.join(BASE_DIR, 'cookie.txt')
        if os.path.exists(built_in):
            try:
                with open(built_in, 'r', encoding='utf-8') as f:
                    cookie = f.read().strip()
                if cookie:
                    return cookie
            except:
                pass
        return None
    else:
        # 开发模式：优先外部cookie.txt，其次内置cookie.txt
        script_dir = os.path.dirname(os.path.abspath(__file__))
        external_cookie = os.path.join(script_dir, '..', 'cookie.txt')
        ext_path = os.path.normpath(external_cookie)
        if os.path.exists(ext_path):
            try:
                with open(ext_path, 'r', encoding='utf-8') as f:
                    cookie = f.read().strip()
                if cookie:
                    return cookie
            except:
                pass
        built_in = os.path.join(BASE_DIR, 'cookie.txt')
        if os.path.exists(built_in):
            try:
                with open(built_in, 'r', encoding='utf-8') as f:
                    cookie = f.read().strip()
                if cookie:
                    return cookie
            except:
                pass
        return None


class ParseRequest(BaseModel):
    url: str


class ParseResponse(BaseModel):
    success: bool
    data: dict = None
    error: str = None


def clean_filename(name: str) -> str:
    if not name:
        return "untitled"
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    if len(name) > 100:
        name = name[:100]
    return name.strip() or "untitled"


def make_ascii_filename(name: str) -> str:
    if not name:
        return "untitled"
    ascii_name = ''.join(c if ord(c) < 128 else '_' for c in name)
    ascii_name = re.sub(r'[<>:"/\\|?*]', '', ascii_name)
    ascii_name = ascii_name.strip() or "untitled"
    if len(ascii_name) > 100:
        ascii_name = ascii_name[:100]
    return ascii_name


def extract_video_id(url: str) -> tuple:
    short_pattern = r'v\.douyin\.com/(\w+)'
    long_pattern = r'douyin\.com/video/(\d+)'
    match = re.search(short_pattern, url)
    if match:
        return match.group(1), "short"
    match = re.search(long_pattern, url)
    if match:
        return match.group(1), "long"
    return None, None


def resolve_short_url(short_url: str) -> str:
    try:
        session = curl_requests.Session()
        response = session.get(short_url, impersonate='chrome110', timeout=30)
        return str(response.url)
    except Exception as e:
        raise ValueError(f"短链接解析失败: {str(e)}")


# 默认Cookie（备选）
DEFAULT_COOKIE = "sessionid=7537e758be7abd22d28c690bcc6a2902; sessionid_ss=7537e758be7abd22d28c690bcc6a2902; ttwid=1%7CPUQ2Gb5i68S9FVipbQi0HSvHNr700RkaWH96QPnaZFg%7C1781923994%7Cf51590910c2bdf87527ce981cdfeb08017754; s_v_web_id=verify_mprui90w_N430is0t_Nvvz_4xz1_Aw5Z_JxnV2L065lIW; uid_tt=79fdc843f312b601e4fcdc56b74a90b9; sid_tt=7537e758be7abd22d28c690bcc6a2902"

# 用户Cookie（从cookie.txt读取）
USER_COOKIE = get_cookie()
ACTIVE_COOKIE = USER_COOKIE or DEFAULT_COOKIE

# 启动检查
if not USER_COOKIE:
    import warnings
    warnings.warn("未找到cookie.txt，将使用内置默认Cookie（可能已过期）。请在backend/cookie.txt中填入自己的Cookie以确保解析正常。")


def get_video_info(url: str) -> dict:
    global ACTIVE_COOKIE
    if 'v.douyin.com' in url:
        resolved_url = resolve_short_url(url)
        video_id, _ = extract_video_id(resolved_url)
        if not video_id:
            raise ValueError("无法从短链接解析视频ID")
    else:
        video_id, _ = extract_video_id(url)
        if not video_id:
            raise ValueError("无法从链接中提取视频ID")

    api_url = (
        f"https://www.douyin.com/aweme/v1/web/aweme/detail/"
        f"?aweme_id={video_id}&aid=6383&channel=channel_pc_web"
    )

    headers = {
        'Cookie': ACTIVE_COOKIE,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.douyin.com/',
    }

    response = curl_requests.get(api_url, impersonate='chrome110', timeout=30, headers=headers)
    data = response.json()
    aweme_detail = data.get('aweme_detail')
    filter_info = data.get('filter_detail', {})

    if not aweme_detail:
        reason = filter_info.get('filter_reason', 'unknown')
        if reason == 'login':
            raise ValueError("Cookie已过期，请更新cookie.txt文件（提示：登录抖音网页版获取最新Cookie）")
        if reason == 'core_dep':
            raise ValueError("Cookie无效或已过期，请更新backend/cookie.txt文件（提示：登录抖音后按F12获取Cookie）")
        raise ValueError(f"视频解析失败({reason})")

    ad = aweme_detail
    video_url = ad.get('video', {}).get('play_addr', {}).get('url_list', [])
    if not video_url:
        video_url = ad.get('video', {}).get('download_addr', {}).get('url_list', [])
    music_url = ad.get('music', {}).get('play_url', {}).get('url_list', [])

    return {
        "video_id": ad.get('aweme_id', video_id),
        "title": ad.get('desc', ''),
        "author": ad.get('author', {}).get('nickname', ''),
        "avatar": ad.get('author', {}).get('avatar_thumb', {}).get('url_list', [''])[0] or '',
        "cover_url": ad.get('video', {}).get('cover', {}).get('url_list', [''])[0] or '',
        "video_url": video_url[0] if video_url else '',
        "music_title": ad.get('music', {}).get('title', ''),
        "music_author": ad.get('music', {}).get('author', ''),
        "music_url": music_url[0] if music_url else '',
        "duration": ad.get('video', {}).get('duration', 0),
    }


@app.get("/")
async def root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "抖音作品解析API"}


@app.get("/health")
async def health():
    return {"status": "ok", "cookie_active": USER_COOKIE is not None}


@app.post("/api/parse", response_model=ParseResponse)
async def parse_url(request: ParseRequest):
    try:
        info = get_video_info(request.url)
        if info.get("video_id"):
            _parse_cache[info["video_id"]] = info
        return ParseResponse(success=True, data=info)
    except ValueError as e:
        return ParseResponse(success=False, error=str(e))
    except Exception as e:
        return ParseResponse(success=False, error=f"解析失败: {str(e)}")


@app.get("/api/info/{video_id}")
async def get_video_info_api(video_id: str):
    if video_id not in _parse_cache:
        raise HTTPException(status_code=404, detail="视频信息未找到")
    return _parse_cache[video_id]


@app.get("/api/download/video/{video_id}")
async def download_video(video_id: str):
    if video_id not in _parse_cache:
        raise HTTPException(status_code=404, detail="视频信息未找到")
    info = _parse_cache[video_id]
    video_url = info.get("video_url")
    if not video_url:
        raise HTTPException(status_code=404, detail="视频URL不存在")
    filename = make_ascii_filename(info.get("title", "video")) + ".mp4"
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.douyin.com/'}
    async with httpx.AsyncClient(follow_redirects=True, timeout=120, headers=headers) as client:
        try:
            response = await client.get(video_url)
            response.raise_for_status()
            content = response.content
        except Exception:
            raise HTTPException(status_code=502, detail="视频下载失败")
    return Response(content=content, media_type="video/mp4",
                   headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/download/cover/{video_id}")
async def download_cover(video_id: str):
    if video_id not in _parse_cache:
        raise HTTPException(status_code=404, detail="视频信息未找到")
    info = _parse_cache[video_id]
    cover_url = info.get("cover_url")
    if not cover_url:
        raise HTTPException(status_code=404, detail="封面URL不存在")
    filename = make_ascii_filename(info.get("title", "cover")) + ".jpg"
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.douyin.com/'}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=headers) as client:
        try:
            response = await client.get(cover_url)
            response.raise_for_status()
            content = response.content
        except Exception:
            raise HTTPException(status_code=502, detail="封面下载失败")
    return Response(content=content, media_type="image/jpeg",
                   headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/download/music/{video_id}")
async def download_music(video_id: str):
    if video_id not in _parse_cache:
        raise HTTPException(status_code=404, detail="视频信息未找到")
    info = _parse_cache[video_id]
    music_url = info.get("music_url")
    if not music_url:
        raise HTTPException(status_code=404, detail="音乐URL不存在")
    filename = make_ascii_filename(info.get("music_title", "music")) + ".mp3"
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.douyin.com/'}
    async with httpx.AsyncClient(follow_redirects=True, timeout=60, headers=headers) as client:
        try:
            response = await client.get(music_url)
            response.raise_for_status()
            content = response.content
        except Exception:
            raise HTTPException(status_code=502, detail="音乐下载失败")
    return Response(content=content, media_type="audio/mpeg",
                   headers={"Content-Disposition": f'attachment; filename="{filename}"'})

import httpx
from starlette.responses import Response
