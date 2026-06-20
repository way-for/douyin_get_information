from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from curl_cffi import requests as curl_requests
import re
import json
import httpx
import os

app = FastAPI(
    title="抖音作品解析API",
    description="抖音视频/音频/文案/图片提取工具",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 获取前端静态文件目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 打包模式下，前端文件在backend目录本身
FRONTEND_DIR = BASE_DIR

# 缓存解析结果
_parse_cache = {}


class ParseRequest(BaseModel):
    url: str


class ParseResponse(BaseModel):
    success: bool
    data: dict = None
    error: str = None


def clean_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    if not name:
        return "untitled"
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    if len(name) > 100:
        name = name[:100]
    return name.strip() or "untitled"


def make_ascii_filename(name: str) -> str:
    """生成仅包含ASCII字符的文件名（用于HTTP header）"""
    if not name:
        return "untitled"
    # 移除非ASCII字符，替换为下划线
    ascii_name = ''.join(c if ord(c) < 128 else '_' for c in name)
    ascii_name = re.sub(r'[<>:"/\\|?*]', '', ascii_name)
    ascii_name = ascii_name.strip() or "untitled"
    if len(ascii_name) > 100:
        ascii_name = ascii_name[:100]
    return ascii_name


def extract_video_id(url: str) -> tuple:
    """从URL中提取视频ID"""
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
    """解析短链接，获取重定向后的长链接"""
    session = curl_requests.Session()
    response = session.get(short_url, impersonate='chrome110', timeout=30)
    return str(response.url)


# 简化版Cookie（核心字段）
DEFAULT_COOKIE = "sessionid=7537e758be7abd22d28c690bcc6a2902; sessionid_ss=7537e758be7abd22d28c690bcc6a2902; ttwid=1%7CPUQ2Gb5i68S9FVipbQi0HSvHNr700RkaWH96QPnaZFg%7C1781923994%7Cf51590910c2bdf87527ce981cdfeb0801777540a73192440821854bcde0d01d7; s_v_web_id=verify_mprui90w_N430is0t_Nvvz_4xz1_Aw5Z_JxnV2L065lIW; uid_tt=79fdc843f312b601e4fcdc56b74a90b9; sid_tt=7537e758be7abd22d28c690bcc6a2902"


def get_video_info(url: str, cookie: str = None) -> dict:
    """获取视频详细信息"""
    use_cookie = cookie or DEFAULT_COOKIE

    # 如果是短链接，先解析为长链接
    if 'v.douyin.com' in url:
        resolved_url = resolve_short_url(url)
        video_id, url_type = extract_video_id(resolved_url)
        if not video_id:
            raise ValueError("无法从短链接中解析视频ID")
    else:
        video_id, url_type = extract_video_id(url)
        if not video_id:
            raise ValueError("无法从链接中提取视频ID")

    api_url = (
        f"https://www.douyin.com/aweme/v1/web/aweme/detail/"
        f"?aweme_id={video_id}&aid=6383&channel=channel_pc_web"
        f"&pc_client_type=1&version_code=190500&version_name=19.5.0"
        f"&cookie_enabled=true&screen_width=1920&screen_height=1080"
        f"&browser_language=zh-CN&browser_platform=Win32"
        f"&browser_name=Chrome&browser_version=120.0.0.0"
    )

    headers = {
        'Cookie': use_cookie,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/',
    }

    response = curl_requests.get(api_url, impersonate='chrome110', timeout=30, headers=headers)

    if response.status_code != 200:
        raise ValueError(f"API请求失败: {response.status_code}")

    data = response.json()
    aweme_detail = data.get('aweme_detail')
    filter_info = data.get('filter_detail', {})

    if not aweme_detail:
        filter_reason = filter_info.get('filter_reason', 'unknown')
        detail_msg = filter_info.get('detail_msg', '视频无法解析')

        if filter_reason == 'login':
            raise ValueError("该视频需要登录才能查看")
        elif filter_reason == 'not_found':
            raise ValueError("视频不存在或已删除")
        elif filter_reason == 'core_dep':
            raise ValueError("视频无法解析（可能被限制或需要Cookie）")
        else:
            raise ValueError(f"视频无法解析: {detail_msg}")

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
    """提供前端页面"""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "抖音作品解析API", "frontend": "not built"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/parse", response_model=ParseResponse)
async def parse_url(request: ParseRequest):
    """解析抖音链接，返回视频信息"""
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
    """获取已解析的视频信息"""
    if video_id not in _parse_cache:
        raise HTTPException(status_code=404, detail="视频信息未找到，请先解析链接")
    return _parse_cache[video_id]


@app.get("/api/download/video/{video_id}")
async def download_video(video_id: str):
    """下载视频"""
    if video_id not in _parse_cache:
        raise HTTPException(status_code=404, detail="视频信息未找到，请先解析链接")

    info = _parse_cache[video_id]
    video_url = info.get("video_url")

    if not video_url:
        raise HTTPException(status_code=404, detail="视频URL不存在")

    filename = make_ascii_filename(info.get("title", "video")) + ".mp4"

    # 带headers下载
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/',
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=120, headers=headers) as client:
        response = await client.get(video_url)
        response.raise_for_status()

    from fastapi.responses import Response
    return Response(
        content=response.content,
        media_type="video/mp4",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/download/cover/{video_id}")
async def download_cover(video_id: str):
    """下载视频封面图"""
    if video_id not in _parse_cache:
        raise HTTPException(status_code=404, detail="视频信息未找到，请先解析链接")

    info = _parse_cache[video_id]
    cover_url = info.get("cover_url")

    if not cover_url:
        raise HTTPException(status_code=404, detail="封面URL不存在")

    filename = make_ascii_filename(info.get("title", "cover")) + ".jpg"

    # 带headers下载
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/',
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=30, headers=headers) as client:
        try:
            response = await client.get(cover_url)
            if response.status_code != 200:
                raise HTTPException(status_code=502, detail=f"封面下载失败: {response.status_code}")
            content = response.content
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"封面下载失败: {str(e)}")

    from fastapi.responses import Response
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/download/music/{video_id}")
async def download_music(video_id: str):
    """下载视频音乐"""
    if video_id not in _parse_cache:
        raise HTTPException(status_code=404, detail="视频信息未找到，请先解析链接")

    info = _parse_cache[video_id]
    music_url = info.get("music_url")

    if not music_url:
        raise HTTPException(status_code=404, detail="音乐URL不存在")

    music_title = info.get("music_title", "music")
    filename = make_ascii_filename(music_title) + ".mp3"

    # 带headers下载
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/',
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=60, headers=headers) as client:
        response = await client.get(music_url)
        response.raise_for_status()

    from fastapi.responses import Response
    return Response(
        content=response.content,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# 提供前端静态文件
@app.get("/{path:path}")
async def serve_frontend(path: str):
    """提供前端静态文件"""
    file_path = os.path.join(FRONTEND_DIR, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    # Fallback to index.html for SPA routing
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404, detail="Not found")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
