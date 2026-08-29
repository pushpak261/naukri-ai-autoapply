"""AI Service — LLM completion, matching, scam detection, match cache."""

from __future__ import annotations

from api.routes import ai_service as ai_service_router
from api.routes import scam_detector as scam_detector_router
from libs.common import make_service_app

app = make_service_app(
    name="ai-service",
    routers=[scam_detector_router, ai_service_router],
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8106)
