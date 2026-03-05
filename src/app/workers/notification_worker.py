async def send_push_notification(user_id: str, title: str, body: str) -> None:
    # TODO: implement FCM/APNs dispatch
    raise NotImplementedError


async def send_email_notification(to: str, subject: str, html: str) -> None:
    # TODO: implement AWS SES dispatch
    raise NotImplementedError
