"""No-network provider used when Gemini is explicitly disabled."""


class OfflineProvider:
    async def generate_content(self, *args, **kwargs):
        raise RuntimeError(
            "Gemini is disabled. This operation requires saved resume/profile facts."
        )

    async def aclose(self):
        pass
