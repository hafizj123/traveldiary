import json
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models.timeline_point import TimelinePoint
from ..models.travel_segment import TravelSegment
from ..models.trip import Trip
from ..models.trip_journal import TripJournal


_TONE_WORDS = {
    "warm": {
        "opener": "This journey unfolded as a gentle sequence of shared moments",
        "closer": "The memories from this route still feel close and easy to revisit.",
    },
    "reflective": {
        "opener": "Looking back, the trip reads like a thoughtful chain of places and pauses",
        "closer": "Taken together, these stops form a trip worth revisiting in memory.",
    },
    "adventurous": {
        "opener": "The trip kept its momentum by moving from one stop to the next with real curiosity",
        "closer": "By the end, the route feels full of movement, discovery, and earned memories.",
    },
    "elegant": {
        "opener": "The journey came together as a polished sequence of destinations and impressions",
        "closer": "It leaves behind a composed travel story with lasting detail and atmosphere.",
    },
}


def _clean(value: Optional[str]) -> str:
    return " ".join(str(value or "").strip().split())


def _format_date(value) -> str:
    return value.strftime("%d %b %Y") if value else ""


def _method_label(method: Optional[str]) -> str:
    labels = {
        "flight": "flight",
        "train": "train",
        "car": "car",
        "bus": "bus",
        "walk": "walk",
        "ferry": "ferry",
        "excursion": "excursion",
        "other": "route",
    }
    return labels.get(_clean(method).lower(), "route")


def _weather_hint(point: TimelinePoint) -> str:
    weather = point.weather_data or {}
    description = _clean(weather.get("description") or weather.get("condition"))
    if not description:
        return ""
    min_temp = weather.get("temp_min")
    max_temp = weather.get("temp_max")
    if min_temp is not None and max_temp is not None:
        return f"The weather around {point.place_name} was {description} with temperatures around {round(min_temp)}-{round(max_temp)}°C."
    return f"The weather around {point.place_name} was {description}."


def _group_points(points: List[TimelinePoint]) -> List[Dict]:
    grouped = OrderedDict()
    for point in sorted(points, key=lambda item: (item.visit_date, item.sequence_no, item.id)):
        key = point.visit_date.isoformat()
        grouped.setdefault(key, []).append(point)

    result = []
    for key, day_points in grouped.items():
        result.append({
            "visit_date": day_points[0].visit_date,
            "points": day_points,
        })
    return result


def _day_transport(segments_by_to_point: Dict[int, TravelSegment], day_points: List[TimelinePoint]) -> str:
    labels = []
    for point in day_points:
        seg = segments_by_to_point.get(point.id)
        if seg:
            labels.append(_method_label(seg.travel_method))
    unique = []
    for label in labels:
        if label not in unique:
            unique.append(label)
    if not unique:
        return ""
    if len(unique) == 1:
        return f"Travel that day centered on {unique[0]} connections."
    return f"Travel that day mixed {' and '.join(unique[:-1])} and {unique[-1]}."


def _point_summary(point: TimelinePoint) -> str:
    user_note = _clean(point.description)
    location = ", ".join(part for part in [point.place_name, point.city, point.country] if _clean(part))
    if user_note:
        lowered = user_note[0].lower() + user_note[1:] if len(user_note) > 1 else user_note.lower()
        return f"At {location}, {lowered}."
    weather = _weather_hint(point)
    if weather:
        return f"{location} marked one of the day's stops. {weather}"
    return f"{location} formed part of the trip's route and gave the day its shape."


def _join_places(place_names: List[str]) -> str:
    cleaned = [_clean(name) for name in place_names if _clean(name)]
    if not cleaned:
        return "the journey"
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{cleaned[0]}, {cleaned[1]}, and {cleaned[2]}"


def _build_journal_title(trip: Trip, grouped_days: List[Dict], companion_text: str, tone: str) -> str:
    trip_title = _clean(trip.title)
    trip_description = _clean(trip.description)
    place_names = []
    for day in grouped_days:
        for point in day["points"]:
            if _clean(point.place_name) and point.place_name not in place_names:
                place_names.append(point.place_name)

    featured_places = _join_places(place_names[:3])

    if tone == "reflective":
        if place_names:
            return f"Looking Back on {featured_places}"
        return f"Reflections from {trip_title or 'the journey'}"
    if tone == "adventurous":
        if place_names:
            return f"Through {featured_places}"
        return f"On the Road with {trip_title or 'this trip'}"
    if tone == "elegant":
        if place_names:
            return f"Postcards from {featured_places}"
        return f"A Journal of {trip_title or 'the journey'}"

    if companion_text and place_names:
        return f"Our Days in {featured_places}"
    if trip_description and len(trip_description) < 90:
        return trip_description
    if place_names:
        return f"Moments from {featured_places}"
    return trip_title or "Travel Journal"


def _build_chapter_heading(day_points: List[TimelinePoint], index: int) -> str:
    place_names = [_clean(point.place_name) for point in day_points if _clean(point.place_name)]
    unique_places = []
    for name in place_names:
      if name not in unique_places:
          unique_places.append(name)

    if not unique_places:
        return f"Day {index}"
    if len(unique_places) == 1:
        return unique_places[0]
    if len(unique_places) == 2:
        return f"From {unique_places[0]} to {unique_places[1]}"
    return f"Between {unique_places[0]} and {unique_places[-1]}"


def _truncate_sentences(sentences: List[str], length_mode: str) -> List[str]:
    if length_mode == "short":
        return sentences[:2]
    if length_mode == "standard":
        return sentences[:4]
    return sentences[:6]


def build_trip_journal_context(trip: Trip, points: List[TimelinePoint], segments: List[TravelSegment], tone: str, length_mode: str) -> Dict:
    grouped_days = _group_points(points)
    segments_by_to_point = {segment.to_point_id: segment for segment in segments}
    return {
        "trip_title": trip.title,
        "trip_description": _clean(trip.description),
        "travel_companions": _clean(trip.travel_companions),
        "date_range": {
            "start": trip.start_date.isoformat() if trip.start_date else None,
            "end": trip.end_date.isoformat() if trip.end_date else None,
            "formatted": f"{_format_date(trip.start_date)} to {_format_date(trip.end_date)}" if trip.start_date and trip.end_date else "",
        },
        "cover_image_url": trip.cover_image_url,
        "tone": tone,
        "length_mode": length_mode,
        "days": [
            {
                "day_index": index,
                "visit_date": day["visit_date"].isoformat(),
                "transport_summary": _day_transport(segments_by_to_point, day["points"]),
                "points": [
                    {
                        "point_id": point.id,
                        "place_name": point.place_name,
                        "city": point.city,
                        "country": point.country,
                        "visit_date": point.visit_date.isoformat(),
                        "description": _clean(point.description),
                        "image_url": point.image_url,
                        "weather_hint": _weather_hint(point),
                    }
                    for point in day["points"]
                ],
            }
            for index, day in enumerate(grouped_days, start=1)
        ],
    }


def build_rule_based_trip_journal_payload(trip: Trip, points: List[TimelinePoint], segments: List[TravelSegment], tone: str, length_mode: str, template_key: str = "editorial") -> Dict:
    tone_key = tone if tone in _TONE_WORDS else "warm"
    tone_words = _TONE_WORDS[tone_key]
    grouped_days = _group_points(points)
    segments_by_to_point = {segment.to_point_id: segment for segment in segments}
    companion_text = _clean(trip.travel_companions)
    trip_description = _clean(trip.description)

    intro_parts = [tone_words["opener"] + "."]
    if companion_text:
        intro_parts.append(f"This trip was shared with {companion_text}.")
    if trip.start_date and trip.end_date:
        intro_parts.append(f"It ran from {_format_date(trip.start_date)} to {_format_date(trip.end_date)}.")
    if trip_description:
        intro_parts.append(trip_description)
    elif grouped_days:
        intro_parts.append(
            f"The route moved through {len(grouped_days)} day{'s' if len(grouped_days) != 1 else ''} and {len(points)} stop{'s' if len(points) != 1 else ''}, building its story from places, movement, and the details captured along the way."
        )

    journal_title = _build_journal_title(trip, grouped_days, companion_text, tone_key)
    chapters = []
    for index, day in enumerate(grouped_days, start=1):
        day_points = day["points"]
        heading_focus = _build_chapter_heading(day_points, index)
        sentences = [f"Day {index} focused on {heading_focus}."]
        transport_line = _day_transport(segments_by_to_point, day_points)
        if transport_line:
            sentences.append(transport_line)
        for point in day_points:
            sentences.append(_point_summary(point))
        if not any(_clean(point.description) for point in day_points):
            sentences.append("Even without written notes for every stop, the timeline still preserves the rhythm of how the day unfolded.")
        body = " ".join(_truncate_sentences(sentences, length_mode))
        chapters.append({
            "chapter_index": index,
            "heading": heading_focus,
            "visit_date": day["visit_date"].isoformat(),
            "body_text": body,
            "point_ids": [point.id for point in day_points],
            "image_urls": [point.image_url for point in day_points if _clean(point.image_url)],
            "locations": [
                {
                    "point_id": point.id,
                    "place_name": point.place_name,
                    "city": point.city,
                    "country": point.country,
                    "visit_date": point.visit_date.isoformat(),
                    "description": point.description,
                    "image_url": point.image_url,
                }
                for point in day_points
            ],
        })

    ending_location = points[-1].place_name if points else trip.title
    return {
        "title": journal_title,
        "intro_text": " ".join(intro_parts),
        "closing_text": f"The journey concluded around {ending_location}. {tone_words['closer']}",
        "tone": tone_key,
        "length_mode": length_mode,
        "content_json": {
            "chapters": chapters,
            "cover_image_url": trip.cover_image_url,
            "travel_companions": companion_text,
            "template_key": template_key,
            "generation_source": "rule_based",
            "provider_label": "Rule-based draft",
        },
    }


def _build_json_prompt(context: Dict) -> str:
    schema = {
        "title": "string",
        "intro_text": "string",
        "closing_text": "string",
        "chapters": [
            {
                "chapter_index": "number",
                "heading": "string",
                "visit_date": "YYYY-MM-DD",
                "body_text": "string",
                "point_ids": ["number"],
            }
        ],
    }
    return (
        "Create a beautiful but grounded travel journal in JSON only. "
        "Use only the facts provided. Do not invent dramatic events, emotions, or activities that are not supported by the trip data. "
        "When notes are sparse, stay conservative and elegant. "
        "Write like a polished personal travel diary, not like a report or itinerary summary. "
        "The journal title must feel memorable, scenic, and human. Avoid generic titles such as place lists, 'X and nearby stops', 'Trip to X', or 'Day 1'. "
        "Prefer evocative titles that still stay faithful to the provided places, atmosphere, companions, and route. "
        "Chapter headings should also avoid sounding generic. Prefer headings like a movement, mood, or route between places when possible. "
        "Return valid JSON with this exact shape:\n"
        f"{json.dumps(schema, indent=2)}\n\n"
        "Trip context:\n"
        f"{json.dumps(context, indent=2, ensure_ascii=False)}"
    )


def _parse_openai_text(data: Dict) -> str:
    output = data.get("output") or []
    texts = []
    for item in output:
        for content in item.get("content") or []:
            text = content.get("text")
            if text:
                texts.append(text)
    if texts:
        return "\n".join(texts)
    return str(data.get("output_text") or "").strip()


def _parse_gemini_text(data: Dict) -> str:
    candidates = data.get("candidates") or []
    texts = []
    for candidate in candidates:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            text = part.get("text")
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def _extract_json_block(text: str) -> Dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object returned")
    return json.loads(cleaned[start:end + 1])


def _merge_ai_payload(trip: Trip, points: List[TimelinePoint], base_payload: Dict, ai_payload: Dict, tone: str, length_mode: str, provider_label: str) -> Dict:
    chapters_by_index = {chapter["chapter_index"]: chapter for chapter in base_payload["content_json"]["chapters"]}
    merged_chapters = []
    for chapter in ai_payload.get("chapters") or []:
        index = chapter.get("chapter_index")
        base_chapter = chapters_by_index.get(index)
        if not base_chapter:
            continue
        merged_chapters.append({
            **base_chapter,
            "heading": _clean(chapter.get("heading")) or base_chapter["heading"],
            "body_text": _clean(chapter.get("body_text")) or base_chapter["body_text"],
        })
    if not merged_chapters:
        raise ValueError("AI response did not include usable chapters")
    merged_chapters.sort(key=lambda item: item["chapter_index"])
    return {
        "title": _clean(ai_payload.get("title")) or base_payload["title"],
        "intro_text": _clean(ai_payload.get("intro_text")) or base_payload["intro_text"],
        "closing_text": _clean(ai_payload.get("closing_text")) or base_payload["closing_text"],
        "tone": tone,
        "length_mode": length_mode,
        "content_json": {
            **base_payload["content_json"],
            "chapters": merged_chapters,
            "generation_source": "ai",
            "provider_label": provider_label,
        },
    }


async def _call_gemini(prompt: str) -> Tuple[Optional[Dict], Optional[str]]:
    api_key = _clean(settings.GEMINI_API_KEY)
    model = _clean(settings.GEMINI_MODEL)
    if not api_key or not model:
        return None, None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                ]
            }
        ]
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        text = _parse_gemini_text(response.json())
    return _extract_json_block(text), f"Gemini ({model})"


async def _call_openai(prompt: str) -> Tuple[Optional[Dict], Optional[str]]:
    api_key = _clean(settings.OPENAI_API_KEY)
    model = _clean(settings.OPENAI_MODEL)
    if not api_key or not model:
        return None, None
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": "You write grounded, elegant travel journals and return valid JSON only."}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt}
                ],
            },
        ],
    }
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        text = _parse_openai_text(response.json())
    return _extract_json_block(text), f"OpenAI ({model})"


async def _generate_ai_payload(trip: Trip, points: List[TimelinePoint], segments: List[TravelSegment], tone: str, length_mode: str) -> Tuple[Optional[Dict], Optional[str]]:
    provider = _clean(settings.AI_JOURNAL_PROVIDER).lower() or "gemini"
    context = build_trip_journal_context(trip, points, segments, tone, length_mode)
    prompt = _build_json_prompt(context)
    if provider == "openai":
        return await _call_openai(prompt)
    if provider == "gemini":
        return await _call_gemini(prompt)
    return None, None


async def upsert_trip_journal(
    db: Session,
    trip: Trip,
    points: List[TimelinePoint],
    segments: List[TravelSegment],
    tone: str,
    length_mode: str,
    use_ai: bool = True,
    template_key: str = "editorial",
) -> TripJournal:
    base_payload = build_rule_based_trip_journal_payload(trip, points, segments, tone, length_mode, template_key=template_key)
    final_payload = base_payload
    if use_ai:
        try:
            ai_payload, provider_label = await _generate_ai_payload(trip, points, segments, tone, length_mode)
            if ai_payload and provider_label:
                final_payload = _merge_ai_payload(trip, points, base_payload, ai_payload, tone, length_mode, provider_label)
        except Exception:
            final_payload = base_payload

    journal = db.query(TripJournal).filter(TripJournal.trip_id == trip.id).first()
    if not journal:
        journal = TripJournal(
            trip_id=trip.id,
            title=final_payload["title"],
            intro_text=final_payload["intro_text"],
            closing_text=final_payload["closing_text"],
            tone=final_payload["tone"],
            length_mode=final_payload["length_mode"],
            content_json=final_payload["content_json"],
        )
        db.add(journal)
        db.flush()
        return journal

    journal.title = final_payload["title"]
    journal.intro_text = final_payload["intro_text"]
    journal.closing_text = final_payload["closing_text"]
    journal.tone = final_payload["tone"]
    journal.length_mode = final_payload["length_mode"]
    journal.content_json = final_payload["content_json"]
    db.flush()
    return journal


def sync_trip_journal_media(journal: TripJournal, trip: Trip, points: List[TimelinePoint]) -> bool:
    content_json = dict(journal.content_json or {})
    point_lookup = {point.id: point for point in points}
    changed = False

    if content_json.get("cover_image_url") != trip.cover_image_url:
        content_json["cover_image_url"] = trip.cover_image_url
        changed = True

    if not content_json.get("template_key"):
        content_json["template_key"] = "editorial"
        changed = True

    next_chapters = []
    for chapter in content_json.get("chapters") or []:
        next_chapter = dict(chapter)
        point_ids = [point_id for point_id in (next_chapter.get("point_ids") or []) if point_id in point_lookup]
        chapter_points = [point_lookup[point_id] for point_id in point_ids]
        image_urls = [_clean(point.image_url) for point in chapter_points if _clean(point.image_url)]
        if next_chapter.get("image_urls") != image_urls:
            next_chapter["image_urls"] = image_urls
            changed = True

        next_locations = []
        for point in chapter_points:
            next_locations.append({
                "point_id": point.id,
                "place_name": point.place_name,
                "city": point.city,
                "country": point.country,
                "visit_date": point.visit_date.isoformat() if point.visit_date else None,
                "description": point.description,
                "image_url": point.image_url,
            })
        if next_chapter.get("locations") != next_locations:
            next_chapter["locations"] = next_locations
            changed = True

        next_chapters.append(next_chapter)

    if content_json.get("chapters") != next_chapters:
        content_json["chapters"] = next_chapters
        changed = True

    if changed:
        journal.content_json = content_json

    return changed
