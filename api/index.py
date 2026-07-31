from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, field_validator, model_validator
from supabase import Client, create_client


load_dotenv()
logger = logging.getLogger("qmenu")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
DEFAULT_STORE_ID = os.getenv("DEFAULT_STORE_ID", "").strip()
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

TABLE_STATUSES = {"available", "soon", "reserved", "occupied"}
ORDER_STATUSES = {"pending", "completed", "cancelled"}
RESERVATION_STATUSES = {"reserved", "waiting", "accepted", "cancelled"}
ACTIVE_RESERVATION_STATUSES = {"reserved", "waiting", "accepted"}
MAX_IMAGE_BYTES = 2 * 1024 * 1024
IMAGE_DATA_PATTERN = re.compile(
    r"^data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=\r\n]+)$",
    re.IGNORECASE,
)

app = FastAPI(
    title="Q-Menu API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

if ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )


@app.get("/", include_in_schema=False)
def redirect_to_login() -> RedirectResponse:
    return RedirectResponse(url="/index.html", status_code=307)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def public_number(value: Any) -> float | int:
    number = float(value)
    return int(number) if number.is_integer() else number


def validate_image_value(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return value
    if value.startswith("data:"):
        match = IMAGE_DATA_PATTERN.fullmatch(value)
        if not match:
            raise ValueError("이미지는 JPEG, PNG 또는 WEBP 형식이어야 합니다.")
        encoded = re.sub(r"\s+", "", match.group(2))
        decoded_size = (len(encoded) * 3) // 4
        if decoded_size > MAX_IMAGE_BYTES:
            raise ValueError("이미지는 2MB 이하여야 합니다.")
    elif len(value) > 2048:
        raise ValueError("이미지 URL이 너무 깁니다.")
    return value


class StoreUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    hours: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=500)
    name_en: str = Field(default="", max_length=120)
    hours_en: str = Field(default="", max_length=200)
    description_en: str = Field(default="", max_length=500)

    @field_validator(
        "name", "hours", "description", "name_en", "hours_en", "description_en"
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class MenuPayload(BaseModel):
    name: Dict[str, str]
    price: float = Field(ge=0)
    currency: str = Field(min_length=1, max_length=8)
    desc: Dict[str, str]
    tags: List[Dict[str, str]] = Field(default_factory=list, max_length=30)
    img: Optional[str] = None
    isSoldOut: bool = False

    @field_validator("name", "desc")
    @classmethod
    def require_korean_text(cls, value: Dict[str, str]) -> Dict[str, str]:
        if not str(value.get("ko", "")).strip():
            raise ValueError("한국어 메뉴명과 설명은 비워 둘 수 없습니다.")
        return {str(key): str(text).strip() for key, text in value.items()}

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("img")
    @classmethod
    def validate_image(cls, value: Optional[str]) -> Optional[str]:
        return validate_image_value(value)


class TablePayload(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    db_id: Optional[str] = None
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    status: Literal["available", "soon", "reserved", "occupied"]
    view: str = Field(default="", max_length=100)
    tag: str = Field(default="", max_length=100)
    capacity: int = Field(default=4, ge=1, le=50)
    table_image: Optional[str] = None
    view_image: Optional[str] = None

    @field_validator("id")
    @classmethod
    def normalize_table_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("table_image", "view_image")
    @classmethod
    def validate_table_images(cls, value: Optional[str]) -> Optional[str]:
        return validate_image_value(value)


class TableLayoutUpdate(BaseModel):
    tables: List[TablePayload] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_table_codes(self) -> "TableLayoutUpdate":
        codes = [table.id for table in self.tables]
        if len(codes) != len(set(codes)):
            raise ValueError("중복된 테이블 코드는 사용할 수 없습니다.")
        return self


class KeywordUpdate(BaseModel):
    keywords: List[str] = Field(max_length=50)

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: List[str]) -> List[str]:
        normalized: List[str] = []
        for value in values:
            keyword = value.strip()
            if not keyword:
                continue
            keyword = keyword if keyword.startswith("#") else f"#{keyword}"
            if len(keyword) > 40:
                raise ValueError("추천 키워드는 40자 이하여야 합니다.")
            if keyword not in normalized:
                normalized.append(keyword)
        return normalized


class OrderCreate(BaseModel):
    table_id: str = Field(min_length=1, max_length=32)
    menu_id: UUID
    quantity: int = Field(ge=1, le=100)
    customer_session_id: UUID
    mode: Literal["web", "store"]

    @field_validator("table_id")
    @classmethod
    def normalize_order_table_code(cls, value: str) -> str:
        return value.strip().upper()


class OrderStatusUpdate(BaseModel):
    status: Literal["pending", "completed", "cancelled"]


class ReservationCreate(BaseModel):
    table_id: str = Field(min_length=1, max_length=32)
    status: Literal["reserved", "waiting"]
    customer_session_id: UUID
    mode: Literal["web", "store"]
    party_size: int = Field(default=0, ge=0, le=50)

    @field_validator("table_id")
    @classmethod
    def normalize_reservation_table_code(cls, value: str) -> str:
        return value.strip().upper()


class ReservationStatusUpdate(BaseModel):
    status: Literal["accepted", "cancelled"]


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    review_text: str = Field(min_length=1, max_length=2000)
    image: Optional[str] = None
    customer_session_id: UUID

    @field_validator("review_text")
    @classmethod
    def strip_review_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("리뷰 내용을 입력해 주세요.")
        return value

    @field_validator("image")
    @classmethod
    def validate_review_image(cls, value: Optional[str]) -> Optional[str]:
        return validate_image_value(value)


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    language: str = Field(default="ko", min_length=2, max_length=10)
    mode: Literal["web", "store"] = "store"

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("AI 질문을 입력해 주세요.")
        return value


class GeminiChatResponse(BaseModel):
    reply: str
    recommended_menu_ids: List[str] = Field(default_factory=list)


def menu_to_public(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row.get("name") or {},
        "price": public_number(row.get("price", 0)),
        "currency": row.get("currency", "KRW"),
        "desc": row.get("description") or {},
        "tags": row.get("tags") or [],
        "img": row.get("image_data") or row.get("image_url") or "",
        "isSoldOut": bool(row.get("is_sold_out", False)),
    }


def table_to_public(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["table_code"],
        "db_id": str(row["id"]),
        "x": public_number(row.get("x", 0)),
        "y": public_number(row.get("y", 0)),
        "status": row.get("status", "available"),
        "view": row.get("view_name") or "",
        "tag": row.get("tag") or "",
        "capacity": int(row.get("capacity", 4)),
        "table_image": row.get("table_image") or "",
        "view_image": row.get("view_image") or "",
    }


def order_to_public(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "table_id": row["table_id"],
        "menu_id": str(row["menu_id"]),
        "menu_name": row["menu_name"],
        "quantity": int(row["quantity"]),
        "total_price": public_number(row["total_price"]),
        "currency": row["currency"],
        "status": row["status"],
        "customer_session_id": row["customer_session_id"],
        "created_at": row["created_at"],
        "updated_at": row.get("updated_at"),
    }


def reservation_to_public(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "table_id": row["table_id"],
        "status": row["status"],
        "customer_session_id": row["customer_session_id"],
        "party_size": int(row.get("party_size") or 0),
        "created_at": row["created_at"],
        "updated_at": row.get("updated_at"),
    }


def review_to_public(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "rating": int(row["rating"]),
        "review_text": row["review_text"],
        "image": row.get("image_data") or "",
        "customer_session_id": row["customer_session_id"],
        "created_at": row["created_at"],
    }


class SupabaseRepository:
    def __init__(self, client: Client, store_id: str) -> None:
        self.client = client
        self.store_id = store_id

    def _run(self, operation: Any, message: str) -> Any:
        try:
            return operation()
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("%s", message)
            raise HTTPException(status_code=502, detail=message) from exc

    def health(self) -> bool:
        try:
            self.client.table("stores").select("id").eq(
                "id", self.store_id
            ).limit(1).execute()
            return True
        except Exception:
            logger.exception("Supabase health check failed")
            return False

    def get_store(self) -> Dict[str, Any]:
        response = self._run(
            lambda: self.client.table("stores")
            .select("*")
            .eq("id", self.store_id)
            .limit(1)
            .execute(),
            "매장 정보를 불러오지 못했습니다.",
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="매장 정보를 찾을 수 없습니다.")
        return response.data[0]

    def update_store(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._run(
            lambda: self.client.table("stores")
            .update({**payload, "updated_at": utc_now()})
            .eq("id", self.store_id)
            .execute(),
            "매장 정보를 저장하지 못했습니다.",
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="매장 정보를 찾을 수 없습니다.")
        return response.data[0]

    def get_menus(self) -> List[Dict[str, Any]]:
        response = self._run(
            lambda: self.client.table("menus")
            .select("*")
            .eq("store_id", self.store_id)
            .order("created_at", desc=True)
            .execute(),
            "메뉴를 불러오지 못했습니다.",
        )
        return response.data or []

    def get_menu(self, menu_id: str) -> Optional[Dict[str, Any]]:
        response = self._run(
            lambda: self.client.table("menus")
            .select("*")
            .eq("store_id", self.store_id)
            .eq("id", menu_id)
            .limit(1)
            .execute(),
            "메뉴를 불러오지 못했습니다.",
        )
        return response.data[0] if response.data else None

    def create_menu(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._run(
            lambda: self.client.table("menus")
            .insert({"store_id": self.store_id, **payload})
            .execute(),
            "메뉴를 등록하지 못했습니다.",
        )
        return response.data[0]

    def update_menu(self, menu_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._run(
            lambda: self.client.table("menus")
            .update({**payload, "updated_at": utc_now()})
            .eq("store_id", self.store_id)
            .eq("id", menu_id)
            .execute(),
            "메뉴를 수정하지 못했습니다.",
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다.")
        return response.data[0]

    def delete_menu(self, menu_id: str) -> None:
        if not self.get_menu(menu_id):
            raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다.")
        self._run(
            lambda: self.client.table("menus")
            .delete()
            .eq("store_id", self.store_id)
            .eq("id", menu_id)
            .execute(),
            "메뉴를 삭제하지 못했습니다.",
        )

    def get_tables(self) -> List[Dict[str, Any]]:
        response = self._run(
            lambda: self.client.table("tables")
            .select("*")
            .eq("store_id", self.store_id)
            .order("sort_order")
            .execute(),
            "좌석 배치를 불러오지 못했습니다.",
        )
        return response.data or []

    def get_table(self, table_code: str) -> Optional[Dict[str, Any]]:
        response = self._run(
            lambda: self.client.table("tables")
            .select("*")
            .eq("store_id", self.store_id)
            .eq("table_code", table_code)
            .limit(1)
            .execute(),
            "좌석 정보를 불러오지 못했습니다.",
        )
        return response.data[0] if response.data else None

    def replace_tables(self, tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = [
            {
                "id": table.get("db_id"),
                "table_code": table["id"],
                "x": table["x"],
                "y": table["y"],
                "status": table["status"],
                "view_name": table.get("view", ""),
                "tag": table.get("tag", ""),
                "capacity": table.get("capacity", 4),
                "table_image": table.get("table_image") or None,
                "view_image": table.get("view_image") or None,
                "sort_order": index,
            }
            for index, table in enumerate(tables, start=1)
        ]
        self._run(
            lambda: self.client.rpc(
                "replace_store_tables",
                {"p_store_id": self.store_id, "p_tables": payload},
            ).execute(),
            "좌석 배치를 저장하지 못했습니다.",
        )
        return self.get_tables()

    def get_keywords(self) -> List[str]:
        return list(self.get_store().get("recommendation_keywords") or [])

    def update_keywords(self, keywords: List[str]) -> List[str]:
        self.update_store({"recommendation_keywords": keywords})
        return keywords

    def get_orders(
        self, customer_session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        def operation() -> Any:
            query = (
                self.client.table("orders")
                .select("*")
                .eq("store_id", self.store_id)
            )
            if customer_session_id:
                query = query.eq("customer_session_id", customer_session_id)
            return query.order("created_at", desc=True).execute()

        response = self._run(operation, "주문을 불러오지 못했습니다.")
        return response.data or []

    def create_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._run(
            lambda: self.client.table("orders")
            .insert({"store_id": self.store_id, **payload})
            .execute(),
            "주문을 등록하지 못했습니다.",
        )
        return response.data[0]

    def update_order_status(
        self, order_id: str, status: str
    ) -> Dict[str, Any]:
        response = self._run(
            lambda: self.client.table("orders")
            .update({"status": status, "updated_at": utc_now()})
            .eq("store_id", self.store_id)
            .eq("id", order_id)
            .execute(),
            "주문 상태를 변경하지 못했습니다.",
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
        return response.data[0]

    def get_reservations(
        self, customer_session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        def operation() -> Any:
            query = (
                self.client.table("reservations")
                .select("*")
                .eq("store_id", self.store_id)
            )
            if customer_session_id:
                query = query.eq("customer_session_id", customer_session_id)
            return query.order("created_at", desc=True).execute()

        response = self._run(operation, "예약을 불러오지 못했습니다.")
        return response.data or []

    def has_active_reservation(self, table_id: str) -> bool:
        response = self._run(
            lambda: self.client.table("reservations")
            .select("id")
            .eq("store_id", self.store_id)
            .eq("table_id", table_id)
            .in_("status", list(ACTIVE_RESERVATION_STATUSES))
            .limit(1)
            .execute(),
            "예약 중복 여부를 확인하지 못했습니다.",
        )
        return bool(response.data)

    def create_reservation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._run(
            lambda: self.client.table("reservations")
            .insert({"store_id": self.store_id, **payload})
            .execute(),
            "예약을 등록하지 못했습니다.",
        )
        return response.data[0]

    def update_reservation_status(
        self, reservation_id: str, status: str
    ) -> Dict[str, Any]:
        existing = self._run(
            lambda: self.client.table("reservations")
            .select("id")
            .eq("store_id", self.store_id)
            .eq("id", reservation_id)
            .limit(1)
            .execute(),
            "예약 정보를 확인하지 못했습니다.",
        )
        if not existing.data:
            raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
        response = self._run(
            lambda: self.client.rpc(
                "update_reservation_and_table",
                {
                    "p_store_id": self.store_id,
                    "p_reservation_id": reservation_id,
                    "p_status": status,
                },
            ).execute(),
            "예약 상태를 변경하지 못했습니다.",
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
        return response.data

    def get_reviews(self) -> List[Dict[str, Any]]:
        response = self._run(
            lambda: self.client.table("reviews")
            .select("*")
            .eq("store_id", self.store_id)
            .order("created_at", desc=True)
            .execute(),
            "리뷰를 불러오지 못했습니다.",
        )
        return response.data or []

    def create_review(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self._run(
            lambda: self.client.table("reviews")
            .insert({"store_id": self.store_id, **payload})
            .execute(),
            "리뷰를 등록하지 못했습니다.",
        )
        return response.data[0]


REPOSITORY_ERROR = ""


def build_repository() -> SupabaseRepository | None:
    global REPOSITORY_ERROR
    if SUPABASE_URL and SUPABASE_SERVICE_KEY and DEFAULT_STORE_ID:
        try:
            UUID(DEFAULT_STORE_ID)
            return SupabaseRepository(
                create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY),
                DEFAULT_STORE_ID,
            )
        except Exception:
            logger.exception("Supabase client initialization failed")
            REPOSITORY_ERROR = "Supabase 설정을 초기화하지 못했습니다."
            return None

    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", SUPABASE_URL),
            ("SUPABASE_SERVICE_KEY", SUPABASE_SERVICE_KEY),
            ("DEFAULT_STORE_ID", DEFAULT_STORE_ID),
        )
        if not value
    ]
    REPOSITORY_ERROR = (
        "필수 Supabase 환경 변수가 없습니다: " + ", ".join(missing)
    )
    return None


repository = build_repository()
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def get_repository() -> SupabaseRepository:
    if repository is None:
        raise HTTPException(
            status_code=503,
            detail=REPOSITORY_ERROR or "데이터베이스가 설정되지 않았습니다.",
        )
    return repository


def menu_payload_to_row(payload: MenuPayload, include_image: bool) -> Dict[str, Any]:
    translatable = {
        "name": payload.name.get("ko", ""),
        "description": payload.desc.get("ko", ""),
        **{
            f"tag_{index}": tag.get("ko", "")
            for index, tag in enumerate(payload.tags)
        },
    }
    generated = auto_translate_fields(translatable)
    name = complete_translation(payload.name, generated, "name")
    description = complete_translation(payload.desc, generated, "description")
    tags = [
        complete_translation(tag, generated, f"tag_{index}")
        for index, tag in enumerate(payload.tags)
    ]
    row: Dict[str, Any] = {
        "name": name,
        "price": payload.price,
        "currency": payload.currency,
        "description": description,
        "tags": tags,
        "is_sold_out": payload.isSoldOut,
    }
    if include_image:
        row["image_data"] = payload.img or None
    return row


def auto_translate_fields(fields: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    """Translate Korean source fields in one AI request, with a safe source fallback."""
    fallback = {
        language: {key: value for key, value in fields.items()}
        for language in ("en", "vi")
    }
    if not gemini_client or not any(fields.values()):
        return fallback
    try:
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=json.dumps(fields, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Translate every JSON value from Korean into natural restaurant-context "
                    "English and Vietnamese. Preserve keys, numbers, time ranges, and hashtag "
                    "prefixes. Return JSON only in this exact shape: "
                    '{"en":{"key":"translation"},"vi":{"key":"translation"}}.'
                ),
                response_mime_type="application/json",
            ),
        )
        parsed = json.loads(response.text or "{}")
        return {
            language: {
                key: str((parsed.get(language) or {}).get(key) or value).strip()
                for key, value in fields.items()
            }
            for language in ("en", "vi")
        }
    except Exception:
        logger.exception("Automatic translation failed")
        return fallback


def complete_translation(
    current: Dict[str, str], generated: Dict[str, Dict[str, str]], field: str
) -> Dict[str, str]:
    korean = str(current.get("ko", "")).strip()
    return {
        "ko": korean,
        "en": str(current.get("en", "")).strip()
        or generated.get("en", {}).get(field, korean),
        "vi": str(current.get("vi", "")).strip()
        or generated.get("vi", {}).get(field, korean),
    }


def store_to_public(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "hours": row.get("hours") or "",
        "description": row.get("description") or "",
        "name_en": row.get("name_en") or "",
        "hours_en": row.get("hours_en") or "",
        "description_en": row.get("description_en") or "",
        "name_i18n": {
            "ko": row["name"],
            "en": row.get("name_en") or row["name"],
            "vi": row.get("name_vi") or row["name"],
        },
        "hours_i18n": {
            "ko": row.get("hours") or "",
            "en": row.get("hours_en") or row.get("hours") or "",
            "vi": row.get("hours_vi") or row.get("hours") or "",
        },
        "description_i18n": {
            "ko": row.get("description") or "",
            "en": row.get("description_en") or row.get("description") or "",
            "vi": row.get("description_vi") or row.get("description") or "",
        },
    }


@app.get("/api/health")
def health() -> Dict[str, Any]:
    database = "misconfigured"
    if repository is not None:
        database = "connected" if repository.health() else "disconnected"
    return {
        "success": database == "connected",
        "message": "Q-Menu API is running",
        "database": database,
        "ai_provider": "gemini",
        "gemini_configured": bool(gemini_client),
        "gemini_model": GEMINI_MODEL,
    }


@app.get("/api/store")
def get_store() -> Dict[str, Any]:
    return store_to_public(get_repository().get_store())


@app.put("/api/store")
def update_store(payload: StoreUpdate) -> Dict[str, Any]:
    source = {
        "name": payload.name,
        "hours": payload.hours,
        "description": payload.description,
    }
    generated = auto_translate_fields(source)
    row = get_repository().update_store(
        {
            "name": payload.name,
            "hours": payload.hours,
            "description": payload.description,
            "name_en": payload.name_en or generated["en"]["name"],
            "hours_en": payload.hours_en or generated["en"]["hours"],
            "description_en": (
                payload.description_en or generated["en"]["description"]
            ),
            "name_vi": generated["vi"]["name"],
            "hours_vi": generated["vi"]["hours"],
            "description_vi": generated["vi"]["description"],
        }
    )
    return {
        "success": True,
        "message": "매장 정보가 저장되었습니다.",
        "store": store_to_public(row),
    }


@app.get("/api/menus")
def get_menus() -> List[Dict[str, Any]]:
    return [menu_to_public(row) for row in get_repository().get_menus()]


@app.post("/api/menus", status_code=201)
def create_menu(payload: MenuPayload) -> Dict[str, Any]:
    row = get_repository().create_menu(
        menu_payload_to_row(payload, include_image=True)
    )
    return {
        "success": True,
        "message": "메뉴가 등록되었습니다.",
        "menu": menu_to_public(row),
    }


@app.put("/api/menus/{menu_id}")
def update_menu(menu_id: UUID, payload: MenuPayload) -> Dict[str, Any]:
    repo = get_repository()
    if not repo.get_menu(str(menu_id)):
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다.")
    row = repo.update_menu(
        str(menu_id),
        menu_payload_to_row(payload, include_image=payload.img is not None),
    )
    return {
        "success": True,
        "message": "메뉴가 수정되었습니다.",
        "menu": menu_to_public(row),
    }


@app.delete("/api/menus/{menu_id}")
def delete_menu(menu_id: UUID) -> Dict[str, Any]:
    get_repository().delete_menu(str(menu_id))
    return {"success": True, "message": "메뉴가 삭제되었습니다."}


@app.get("/api/tables")
def get_tables() -> List[Dict[str, Any]]:
    return [table_to_public(row) for row in get_repository().get_tables()]


@app.put("/api/tables")
def update_tables(payload: TableLayoutUpdate) -> Dict[str, Any]:
    rows = get_repository().replace_tables(
        [table.model_dump() for table in payload.tables]
    )
    return {
        "success": True,
        "message": "좌석 배치가 저장되었습니다.",
        "tables": [table_to_public(row) for row in rows],
    }


@app.get("/api/keywords")
def get_keywords() -> Dict[str, Any]:
    return {"keywords": get_repository().get_keywords()}


@app.put("/api/keywords")
def update_keywords(payload: KeywordUpdate) -> Dict[str, Any]:
    keywords = get_repository().update_keywords(payload.keywords)
    return {
        "success": True,
        "message": "추천 키워드가 저장되었습니다.",
        "keywords": keywords,
    }


@app.get("/api/orders")
def get_orders(
    customer_session_id: Optional[UUID] = Query(default=None),
) -> List[Dict[str, Any]]:
    session_id = str(customer_session_id) if customer_session_id else None
    return [
        order_to_public(row)
        for row in get_repository().get_orders(session_id)
    ]


@app.post("/api/orders", status_code=201)
def create_order(payload: OrderCreate) -> Dict[str, Any]:
    if payload.mode == "web":
        raise HTTPException(
            status_code=403,
            detail="웹 탐색 모드에서는 주문할 수 없습니다.",
        )
    repo = get_repository()
    menu = repo.get_menu(str(payload.menu_id))
    if not menu:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다.")
    if menu.get("is_sold_out"):
        raise HTTPException(status_code=409, detail="품절된 메뉴는 주문할 수 없습니다.")
    if not repo.get_table(payload.table_id):
        raise HTTPException(status_code=404, detail="테이블을 찾을 수 없습니다.")

    row = repo.create_order(
        {
            "table_id": payload.table_id,
            "menu_id": str(payload.menu_id),
            "menu_name": (menu.get("name") or {}).get("ko", ""),
            "quantity": payload.quantity,
            "total_price": float(menu["price"]) * payload.quantity,
            "currency": menu.get("currency", "KRW"),
            "status": "pending",
            "customer_session_id": str(payload.customer_session_id),
        }
    )
    order = order_to_public(row)
    return {
        "success": True,
        "message": "주문이 완료되었습니다.",
        "order_id": order["id"],
        "order": order,
    }


@app.put("/api/orders/{order_id}/status")
def update_order_status(
    order_id: UUID, payload: OrderStatusUpdate
) -> Dict[str, Any]:
    row = get_repository().update_order_status(str(order_id), payload.status)
    return {
        "success": True,
        "message": "주문 상태가 변경되었습니다.",
        "order": order_to_public(row),
    }


@app.get("/api/reservations")
def get_reservations(
    customer_session_id: Optional[UUID] = Query(default=None),
) -> List[Dict[str, Any]]:
    session_id = str(customer_session_id) if customer_session_id else None
    return [
        reservation_to_public(row)
        for row in get_repository().get_reservations(session_id)
    ]


@app.post("/api/reservations", status_code=201)
def create_reservation(payload: ReservationCreate) -> Dict[str, Any]:
    if payload.mode == "web":
        raise HTTPException(
            status_code=403,
            detail="웹 탐색 모드에서는 예약하거나 대기할 수 없습니다.",
        )
    repo = get_repository()
    table = repo.get_table(payload.table_id)
    if not table:
        raise HTTPException(status_code=404, detail="테이블을 찾을 수 없습니다.")
    session_id = str(payload.customer_session_id)
    if repo.has_active_reservation(payload.table_id):
        raise HTTPException(
            status_code=409,
            detail="같은 좌석에 진행 중인 예약 또는 대기 요청이 있습니다.",
        )

    requested_status = (
        "reserved" if table.get("status") == "available" else "waiting"
    )
    row = repo.create_reservation(
        {
            "table_id": payload.table_id,
            "status": requested_status,
            "customer_session_id": session_id,
            "party_size": payload.party_size,
        }
    )
    reservation = reservation_to_public(row)
    return {
        "success": True,
        "message": (
            "예약 요청이 등록되었습니다."
            if requested_status == "reserved"
            else "웨이팅 요청이 등록되었습니다."
        ),
        "reservation_id": reservation["id"],
        "reservation": reservation,
    }


@app.put("/api/reservations/{reservation_id}/status")
def update_reservation_status(
    reservation_id: UUID, payload: ReservationStatusUpdate
) -> Dict[str, Any]:
    # Supabase 구현은 예약과 좌석 상태를 SQL 함수 안에서 함께 변경한다.
    row = get_repository().update_reservation_status(
        str(reservation_id), payload.status
    )
    return {
        "success": True,
        "message": "예약 상태가 변경되었습니다.",
        "reservation": reservation_to_public(row),
    }


@app.get("/api/reviews")
def get_reviews() -> List[Dict[str, Any]]:
    return [review_to_public(row) for row in get_repository().get_reviews()]


@app.post("/api/reviews", status_code=201)
def create_review(payload: ReviewCreate) -> Dict[str, Any]:
    row = get_repository().create_review(
        {
            "rating": payload.rating,
            "review_text": payload.review_text,
            "image_data": payload.image or None,
            "customer_session_id": str(payload.customer_session_id),
        }
    )
    return {
        "success": True,
        "message": "리뷰가 등록되었습니다.",
        "review": review_to_public(row),
    }


@app.get("/api/queue/status")
def get_queue_status() -> Dict[str, Any]:
    repo = get_repository()
    waiting = [
        row for row in repo.get_reservations() if row["status"] == "waiting"
    ]
    tables = repo.get_tables()
    occupied_count = sum(
        1 for table in tables if table.get("status") == "occupied"
    )
    teams_ahead = len(waiting)
    people_ahead = sum(int(row.get("party_size") or 0) for row in waiting)
    turnover_base = max(1, occupied_count)
    est_time = (
        max(5, round(teams_ahead * 60 / turnover_base))
        if teams_ahead
        else 0
    )
    return {
        "success": True,
        "teams_ahead": teams_ahead,
        "people_ahead": people_ahead,
        "est_time_mins": est_time,
    }


@app.post("/api/chat")
def chat(payload: ChatRequest) -> Dict[str, Any]:
    language_names = {"ko": "Korean", "en": "English", "vi": "Vietnamese"}
    fallback_messages = {
        "ko": "현재 AI 추천 서비스를 이용할 수 없습니다. 전체 메뉴에서 직접 확인해주세요.",
        "en": "The AI recommendation service is currently unavailable. Please check the full menu.",
        "vi": "Dịch vụ gợi ý AI hiện không khả dụng. Vui lòng xem toàn bộ thực đơn.",
    }
    fallback = {
        "success": False,
        "reply": fallback_messages.get(payload.language, fallback_messages["ko"]),
        "recommended_menu_ids": [],
    }
    if not gemini_client:
        return fallback

    try:
        repo = get_repository()
        store = repo.get_store()
        available_menus = [
            menu_to_public(row)
            for row in repo.get_menus()
            if not row.get("is_sold_out")
        ]
        tables = [table_to_public(row) for row in repo.get_tables()]
        table_summary: Dict[str, Dict[str, int]] = {
            "indoor": {},
            "terrace": {},
            "total": {},
        }
        for table in tables:
            area = (
                "terrace"
                if table.get("view") == "테라스" or float(table["x"]) >= 70
                else "indoor"
            )
            status = table["status"]
            table_summary[area][status] = (
                table_summary[area].get(status, 0) + 1
            )
            table_summary["total"][status] = (
                table_summary["total"].get(status, 0) + 1
            )

        mode_instruction = (
            "웹 탐색 모드이므로 주문, 예약, 웨이팅은 불가능하다고 안내하세요."
            if payload.mode == "web"
            else "매장 모드이므로 메뉴와 좌석 안내를 제공할 수 있습니다."
        )
        system_prompt = f"""
당신은 레스토랑 Q-Menu의 친절한 AI 메뉴 및 좌석 안내 도우미입니다.
응답 언어: {language_names.get(payload.language, payload.language)}. 다른 언어를 섞지 마세요.
동작 모드: {payload.mode}. {mode_instruction}

매장 정보:
{json.dumps(store, ensure_ascii=False, default=str)}

판매 중인 메뉴:
{json.dumps(available_menus, ensure_ascii=False)}

최신 좌석 배치:
{json.dumps(tables, ensure_ascii=False)}

좌석 상태 요약:
{json.dumps(table_summary, ensure_ascii=False)}

좌석 질문은 최신 좌석 배치만 근거로 답하세요.
메뉴 추천은 판매 중인 메뉴에서 1~3개만 고르고 해당 메뉴의 id를 반환하세요.
목록에 없는 메뉴 ID를 만들지 마세요.
반드시 다음 JSON 형식만 반환하세요:
{{
  "reply": "사용자에게 보여줄 답변",
  "recommended_menu_ids": ["메뉴 UUID"]
}}
""".strip()
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=payload.query,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=GeminiChatResponse,
            ),
        )
        if isinstance(response.parsed, GeminiChatResponse):
            parsed = response.parsed.model_dump()
        elif isinstance(response.parsed, dict):
            parsed = response.parsed
        else:
            parsed = json.loads(response.text or "{}")
        valid_ids = {menu["id"] for menu in available_menus}
        recommended_ids = [
            str(menu_id)
            for menu_id in parsed.get("recommended_menu_ids", [])
            if str(menu_id) in valid_ids
        ][:3]
        return {
            "success": True,
            "reply": str(parsed.get("reply") or "전체 메뉴를 확인해 주세요."),
            "recommended_menu_ids": recommended_ids,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Gemini chat request failed")
        return fallback
