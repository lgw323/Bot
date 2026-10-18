"""Admin control never creates shell strings or changes a release itself."""

from discordbot.operations.ports.deployment import ManualPort, Responder
from discordbot.platform.errors import AppError


class ManualOperations:
    def __init__(self, master: int, port: ManualPort) -> None:
        self.master, self.port = master, port

    async def request(self, user: int, operation: str, receipt: str, responder: Responder) -> None:
        if user != self.master:
            await responder.reply("이 버튼을 사용할 권한이 없습니다.", ephemeral=True)
            return
        if operation not in {"update", "restart"}:
            await responder.reply("지원하지 않는 운영 요청입니다.", ephemeral=True)
            return
        try:
            result = await self.port.accept(operation, receipt)
        except AppError:
            result = "failed"
        text = {"accepted": "🔄 요청을 접수했습니다.", "already_running": "이미 업데이트 또는 재시작이 진행 중입니다.",
                "failed": "❌ 운영 요청 처리에 실패했습니다."}.get(result, "❌ 운영 요청 처리에 실패했습니다.")
        await responder.reply(text, ephemeral=True)
