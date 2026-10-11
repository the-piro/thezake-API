import uuid
from datetime import datetime
from urllib.parse import urlparse

from curl_cffi import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

API_URL = "https://api.mxplayer.in/v1/web/detail/video"
BASE_URL = "https://www.mxplayer.in"


def mxplayer(url: str):
    parsed = urlparse(url)

    if parsed.hostname not in {"mxplayer.in", "www.mxplayer.in"}:
        raise ValueError("Invalid MX Player URL")

    path = parsed.path.rstrip("/")
    content_id = path.split("-")[-1]

    if not content_id:
        raise ValueError("Content ID not found")

    content_type = "show" if "/show/" in path else "movie"

    params = {
        "type": content_type,
        "id": content_id,
        "userid": str(uuid.uuid4()),
        "platform": "com.mxplay.desktop",
    }

    headers = {
        "Referer": BASE_URL + "/",
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    response = requests.get(
        API_URL,
        params=params,
        headers=headers,
        impersonate="chrome",
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    if not data.get("title"):
        raise ValueError("Metadata not found")

    def image_url(path):
        if not path:
            return None

        if path.startswith(("http://", "https://")):
            return path

        return "https://qqcdnpictest.mxplay.com/" + path.lstrip("/")

    def get_image(items, image_type):
        for item in items or []:
            if item.get("type") == image_type:
                return image_url(item.get("url"))
        return None

    def get_contributors(role):
        result = []

        for person in data.get("contributors") or []:
            person_type = (person.get("type") or "").lower()
            person_role = (person.get("role") or "").lower()

            if role == "directors":
                matched = (
                    "director" in person_type
                    or "director" in person_role
                )
            else:
                matched = person_type == "actor" or person_role == "actor"

            if matched:
                result.append({
                    "name": person.get("name"),
                    "type": person.get("type"),
                    "role": person.get("role"),
                    "id": person.get("id"),
                    "image": get_image(
                        person.get("imageInfo"),
                        "square",
                    ),
                })

        return result

    image_info = data.get("imageInfo") or []
    title_images = data.get("titleContentImageInfo") or []
    images = data.get("image") or {}
    publisher = data.get("publisher") or {}

    landscape = get_image(image_info, "bigpic")
    portrait = get_image(image_info, "portrait")
    cover = get_image(
        title_images,
        "banner_and_static_bg_desktop",
    )
    logo = get_image(title_images, "title_desktop")

    if not landscape:
        landscape = image_url(images.get("16x9"))

    if not portrait:
        portrait = image_url(images.get("2x3"))

    preview_info = data.get("gifVideoUrlInfo") or []

    preview = {
        "landscape": get_image(preview_info, "bigpic"),
        "portrait": image_url(
            (data.get("gifVideoUrl") or {}).get("2x3")
        ),
    }

    release_date = data.get("releaseDate")

    if release_date:
        try:
            release_date = datetime.fromisoformat(
                release_date.replace("Z", "+00:00")
            ).date().isoformat()
        except ValueError:
            pass

    web_url = data.get("webUrl")

    return {
        "title": data.get("title"),
        "images": {
            "landscape": landscape,
            "portrait": portrait,
            "cover": cover,
            "logo": logo,
        },
        "preview": preview,
        "description": data.get("description"),
        "release_date": release_date,
        "duration": data.get("duration"),
        "id": data.get("id"),
        "type": data.get("type"),
        "language": [
            item.get("name")
            for item in data.get("languagesDetails") or []
            if item.get("name")
        ],
        "genres": [
            item.get("name")
            for item in data.get("genresDetails") or []
            if item.get("name")
        ],
        "cast": get_contributors("cast"),
        "directors": get_contributors("directors"),
        "publisher": publisher.get("name"),
        "tags": [
            item.get("name")
            for item in data.get("tags") or []
            if item.get("name")
        ],
        "seek_thumbnails": [
            {
                "url": image_url(item.get("url")),
                "total": item.get("total"),
                "width": item.get("width"),
                "height": item.get("height"),
                "interval": item.get("interval"),
                "columns": item.get("column"),
                "rows": item.get("row"),
            }
            for item in data.get("seekThumbnail") or []
        ],
        "url": (
            BASE_URL + web_url
            if web_url and web_url.startswith("/")
            else web_url
        ),
    }


@router.get("/mxplayer")
def mxplayer_endpoint(url: str = Query(...)):
    try:
        return mxplayer(url)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except requests.errors.RequestsError as e:
        raise HTTPException(
            status_code=502,
            detail=f"MX Player API error: {e}",
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
