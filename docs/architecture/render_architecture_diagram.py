from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "overall-architecture.png"

WIDTH = 2200
HEIGHT = 1450

BG = "#F7FAF8"
TEXT = "#173D33"
SUBTEXT = "#53786D"
BORDER = "#D6E6DF"
ARROW = "#2F7D5A"

AMPLIFY = "#D7F3E4"
AUTH = "#E2F0FF"
API = "#F4E7D3"
STORE = "#EAF5EF"
WORKFLOW = "#FDEBD8"
ANALYTICS = "#EEE8FF"
MONITOR = "#FFF5D6"


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: Iterable[str] = (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


TITLE_FONT = load_font(52, bold=True)
SECTION_FONT = load_font(30, bold=True)
BOX_TITLE_FONT = load_font(28, bold=True)
BOX_BODY_FONT = load_font(22)
SMALL_FONT = load_font(20)


def rounded_box(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], fill: str, title: str, lines: list[str]) -> None:
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=24, fill=fill, outline=BORDER, width=3)
    draw.text((x1 + 24, y1 + 20), title, font=BOX_TITLE_FONT, fill=TEXT)
    y = y1 + 66
    for line in lines:
        draw.text((x1 + 24, y), line, font=BOX_BODY_FONT, fill=SUBTEXT)
        y += 30


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], width: int = 6) -> None:
    draw.line([start, end], fill=ARROW, width=width)
    ex, ey = end
    sx, sy = start
    if abs(ex - sx) >= abs(ey - sy):
        direction = 1 if ex > sx else -1
        draw.polygon(
            [(ex, ey), (ex - 18 * direction, ey - 10), (ex - 18 * direction, ey + 10)],
            fill=ARROW,
        )
    else:
        direction = 1 if ey > sy else -1
        draw.polygon(
            [(ex, ey), (ex - 10, ey - 18 * direction), (ex + 10, ey - 18 * direction)],
            fill=ARROW,
        )


def label(draw: ImageDraw.ImageDraw, text: str, pos: tuple[int, int]) -> None:
    draw.text(pos, text, font=SMALL_FONT, fill=SUBTEXT)


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    draw.text((70, 45), "Smart Personal Finance Tracker", font=TITLE_FONT, fill=TEXT)
    draw.text(
        (72, 108),
        "AWS architecture for the public web app, event pipeline, analytics, and monitoring",
        font=SECTION_FONT,
        fill=SUBTEXT,
    )

    # Frontend/Auth/API
    rounded_box(draw, (80, 210, 500, 360), AMPLIFY, "AWS Amplify Hosting", ["React + Vite public web app", "BrowserRouter SPA"])
    rounded_box(draw, (620, 210, 970, 360), AUTH, "Amazon Cognito", ["Sign up", "Login", "User session auth"])
    rounded_box(draw, (1090, 210, 1480, 360), API, "Amazon API Gateway", ["REST APIs for app, uploads,", "transactions, alerts, analytics"])

    # Backend compute
    rounded_box(draw, (80, 470, 470, 650), API, "Backend Lambda APIs", ["Create/Get user profile", "Upload URL + transaction CRUD", "Monthly summary + category spending"])
    rounded_box(draw, (540, 470, 980, 650), ANALYTICS, "Analytics & ML Lambdas", ["Analytics overview", "Predictions endpoint", "RDS aggregate writes"])

    # Storage
    rounded_box(draw, (1080, 470, 1460, 620), STORE, "DynamoDB", ["UsersTable", "TransactionsTable", "UploadsTable"])
    rounded_box(draw, (1530, 470, 1910, 620), STORE, "Amazon S3", ["Statements bucket", "Pre-signed upload target"])
    rounded_box(draw, (1080, 680, 1460, 830), ANALYTICS, "Amazon RDS MySQL", ["Reporting database", "Aggregated analytics tables"])
    rounded_box(draw, (1530, 680, 1910, 830), ANALYTICS, "Secrets Manager", ["DB credentials", "ML config"])

    # Workflow
    rounded_box(draw, (80, 780, 430, 930), WORKFLOW, "EventBridge", ["Detects new S3 uploads"])
    rounded_box(draw, (500, 780, 850, 930), WORKFLOW, "Step Functions", ["Workflow orchestration", "Success/failure branching"])
    rounded_box(draw, (920, 780, 1250, 930), WORKFLOW, "SQS Queue", ["Async buffer for statements"])
    rounded_box(draw, (1320, 780, 1720, 980), WORKFLOW, "Processor Lambda", ["Parses statements", "Infers categories", "Writes transactions + alerts"])
    rounded_box(draw, (1780, 780, 2100, 930), WORKFLOW, "Amazon SNS", ["Threshold alerts", "Processed/failed email"])

    # Monitoring
    rounded_box(draw, (780, 1090, 1240, 1260), MONITOR, "CloudWatch", ["Dashboard", "Lambda metrics", "RDS health + alarms"])
    rounded_box(draw, (1320, 1090, 1780, 1260), ANALYTICS, "SageMaker-ready Path", ["Prediction integration hook", "Optional hosted model endpoint"])

    # User and data flow arrows
    arrow(draw, (500, 285), (620, 285))
    arrow(draw, (970, 285), (1090, 285))
    arrow(draw, (1285, 360), (1285, 470))
    arrow(draw, (1480, 285), (1560, 285))
    label(draw, "App calls", (1185, 245))

    arrow(draw, (275, 360), (275, 470))
    arrow(draw, (760, 360), (760, 470))
    label(draw, "Authenticated app requests", (350, 390))

    arrow(draw, (470, 550), (540, 550))
    arrow(draw, (980, 550), (1080, 550))
    arrow(draw, (980, 760), (1120, 760))
    arrow(draw, (760, 650), (760, 740))
    arrow(draw, (1710, 620), (1710, 680))
    arrow(draw, (1270, 620), (1270, 680))

    arrow(draw, (1720, 845), (1780, 845))
    arrow(draw, (1910, 545), (1910, 760))
    arrow(draw, (430, 855), (500, 855))
    arrow(draw, (850, 855), (920, 855))
    arrow(draw, (1250, 855), (1320, 855))
    arrow(draw, (1520, 980), (1270, 980))
    arrow(draw, (1270, 980), (1270, 680))
    arrow(draw, (1410, 980), (1410, 620))

    label(draw, "Statement upload", (1640, 250))
    label(draw, "Event-driven processing", (760, 735))
    label(draw, "Reporting aggregates", (1095, 645))

    arrow(draw, (980, 1175), (1240, 1175))
    arrow(draw, (1520, 980), (1520, 1090))
    arrow(draw, (1200, 830), (1100, 1090))
    arrow(draw, (760, 650), (890, 1090))

    # Footer bullets
    draw.text((82, 1315), "Why it is smart:", font=SECTION_FONT, fill=TEXT)
    bullets = [
        "Automatic bank statement ingestion and parsing",
        "Merchant-based category inference and spending summaries",
        "Threshold alerts and event-driven workflow automation",
        "Analytics dashboard backed by API + RDS aggregates",
        "Prediction-ready ML integration and CloudWatch observability",
    ]
    y = 1360
    for item in bullets:
        draw.text((95, y), f"• {item}", font=SMALL_FONT, fill=SUBTEXT)
        y += 28

    image.save(OUTPUT)
    print(f"Saved {OUTPUT}")


if __name__ == "__main__":
    main()
