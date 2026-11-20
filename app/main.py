import os, json, asyncio, threading, base64, sqlite3
from pathlib import Path
from contextlib import closing

from dotenv import load_dotenv
from groq import Groq
import edge_tts

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from gladiaio_sdk import GladiaClient, LiveV2InitRequest


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

GLADIA_API_KEY = os.getenv("GLADIA_API_KEY")
GLADIA_API_URL = os.getenv(
    "GLADIA_API_URL", "https://api.gladia.io"
)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv(
    "GROQ_MODEL", "openai/gpt-oss-120b"
)

# Keep the existing database.
DB_PATH = BASE_DIR / "karachi_kitchen.db"

client_groq = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

app = FastAPI(title="Zayqa Restaurant POS")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static"
)


# MENU
SAMPLE_MENU = [
    ("PK001", "Chicken Biryani", "Pakistani", 450, "Aromatic chicken biryani"),
    ("PK002", "Beef Biryani", "Pakistani", 520, "Spiced beef biryani"),
    ("PK003", "Chicken Karahi", "Pakistani", 1250, "Traditional chicken karahi"),
    ("PK004", "Chicken Handi", "Pakistani", 1350, "Creamy chicken handi"),
    ("BBQ01", "Seekh Kebab", "BBQ", 380, "Grilled seekh kebab"),
    ("BBQ02", "Chicken Tikka", "BBQ", 420, "Smoky chicken tikka"),
    ("CH001", "Chicken Chowmein", "Chinese", 550, "Chicken noodles with vegetables"),
    ("CH002", "Chicken Manchurian", "Chinese", 650, "Chicken in Manchurian sauce"),
    ("CH003", "Egg Fried Rice", "Chinese", 420, "Wok-fried egg rice"),
    ("FF001", "Chicken Burger", "Fast Food", 650, "Crispy chicken burger"),
    ("FF002", "Zinger Burger", "Fast Food", 720, "Spicy crispy zinger burger"),
    ("FF003", "French Fries", "Fast Food", 250, "Golden crispy fries"),
    ("BV001", "Cold Drink", "Beverages", 100, "Chilled soft drink"),
    ("BV002", "Mineral Water", "Beverages", 80, "Bottled drinking water"),
    ("BV003", "Fresh Lime", "Beverages", 180, "Fresh lime drink"),
    ("DS001", "Gulab Jamun", "Desserts", 180, "Traditional sweet dessert")
]


# DATABASE
def get_db():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def initialize_database():
    with closing(get_db()) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS menu_items(
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            price INTEGER NOT NULL,
            description TEXT,
            available INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_number INTEGER NOT NULL,
            order_type TEXT DEFAULT 'dine-in',
            status TEXT DEFAULT 'New',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT(datetime('now','localtime')),
            updated_at TEXT DEFAULT(datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS order_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            menu_item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price INTEGER NOT NULL,
            UNIQUE(order_id, menu_item_id),
            FOREIGN KEY(order_id)
                REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY(menu_item_id)
                REFERENCES menu_items(id)
        );

        CREATE TABLE IF NOT EXISTS order_activity(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT DEFAULT(datetime('now','localtime')),
            FOREIGN KEY(order_id)
                REFERENCES orders(id) ON DELETE CASCADE
        );
        """)

        for item in SAMPLE_MENU:
            c.execute("""
                INSERT OR IGNORE INTO menu_items
                (id,name,category,price,description)
                VALUES(?,?,?,?,?)
            """, item)

        c.commit()


initialize_database()


# MENU HELPERS
def get_menu():
    with closing(get_db()) as c:
        rows = c.execute("""
            SELECT * FROM menu_items
            WHERE available=1
            ORDER BY category,name
        """).fetchall()

        return [dict(r) for r in rows]


# ORDER HELPERS
def get_order_details(c, oid):
    row = c.execute(
        "SELECT * FROM orders WHERE id=?", (oid,)
    ).fetchone()

    if not row:
        return None

    items = c.execute("""
        SELECT oi.menu_item_id,m.name,m.category,
               oi.quantity,oi.unit_price,
               (oi.quantity*oi.unit_price) AS line_total
        FROM order_items oi
        JOIN menu_items m ON m.id=oi.menu_item_id
        WHERE oi.order_id=?
        ORDER BY m.category,m.name
    """, (oid,)).fetchall()

    result = dict(row)
    result["items"] = [dict(x) for x in items]
    result["total"] = sum(x["line_total"] for x in items)
    result["activity"] = []

    return result


def get_all_orders():
    with closing(get_db()) as c:
        rows = c.execute(
            "SELECT id FROM orders ORDER BY id DESC"
        ).fetchall()

        return [
            get_order_details(c, r["id"])
            for r in rows
        ]


def add_activity(c, oid, message):
    c.execute(
        "INSERT INTO order_activity(order_id,message) VALUES(?,?)",
        (oid, message)
    )


# ORDER PROCESSING
def process_order_command(command):
    table = command.get("table_number")
    operations = command.get("operations", [])

    if not isinstance(table, int) or not 1 <= table <= 100:
        raise ValueError("Please specify a table number from 1 to 100.")

    if not operations:
        raise ValueError("Please tell me which menu item to add or change.")

    with closing(get_db()) as c:
        c.execute("BEGIN")

        existing = c.execute("""
            SELECT id FROM orders
            WHERE table_number=?
            AND status IN ('New','Preparing')
            ORDER BY id DESC LIMIT 1
        """, (table,)).fetchone()

        if existing:
            oid = existing["id"]
        else:
            cur = c.execute("""
                INSERT INTO orders(table_number,order_type,status)
                VALUES(?,'dine-in','New')
            """, (table,))

            oid = cur.lastrowid

            add_activity(
                c, oid, f"New dine-in order for Table {table}"
            )

        changes = []

        for op in operations:
            action = str(op.get("action", "add")).lower()
            iid = str(op.get("item_id", "")).upper()
            qty = op.get("quantity", 1)

            if not isinstance(qty, int) or not 1 <= qty <= 50:
                raise ValueError("Quantity must be between 1 and 50.")

            item = c.execute("""
                SELECT id,name,price FROM menu_items
                WHERE id=? AND available=1
            """, (iid,)).fetchone()

            if not item:
                raise ValueError(f"Menu item not found: {iid}")

            old = c.execute("""
                SELECT quantity FROM order_items
                WHERE order_id=? AND menu_item_id=?
            """, (oid, iid)).fetchone()

            if action == "add":
                if old:
                    c.execute("""
                        UPDATE order_items
                        SET quantity=quantity+?
                        WHERE order_id=? AND menu_item_id=?
                    """, (qty, oid, iid))
                else:
                    c.execute("""
                        INSERT INTO order_items
                        (order_id,menu_item_id,quantity,unit_price)
                        VALUES(?,?,?,?)
                    """, (oid, iid, qty, item["price"]))

                changes.append(f"Added {qty} {item['name']}")

            elif action == "remove":
                if not old:
                    changes.append(f"{item['name']} was not on this order")

                elif qty >= old["quantity"]:
                    c.execute("""
                        DELETE FROM order_items
                        WHERE order_id=? AND menu_item_id=?
                    """, (oid, iid))

                    changes.append(f"Removed {item['name']}")

                else:
                    c.execute("""
                        UPDATE order_items
                        SET quantity=quantity-?
                        WHERE order_id=? AND menu_item_id=?
                    """, (qty, oid, iid))

                    changes.append(f"Removed {qty} {item['name']}")

            elif action == "set":
                c.execute("""
                    INSERT INTO order_items
                    (order_id,menu_item_id,quantity,unit_price)
                    VALUES(?,?,?,?)
                    ON CONFLICT(order_id,menu_item_id)
                    DO UPDATE SET
                    quantity=excluded.quantity,
                    unit_price=excluded.unit_price
                """, (oid, iid, qty, item["price"]))

                changes.append(
                    f"Set {item['name']} quantity to {qty}"
                )

            else:
                raise ValueError("Unsupported operation.")

        c.execute("""
            UPDATE orders
            SET notes=?,updated_at=datetime('now','localtime')
            WHERE id=?
        """, (str(command.get("notes", ""))[:300], oid))

        add_activity(c, oid, "; ".join(changes))
        c.commit()

        return get_order_details(c, oid), changes


# DASHBOARD WEBSOCKET
dashboard_connections = set()


async def broadcast_update(data):
    gone = []

    for ws in list(dashboard_connections):
        try:
            await ws.send_json(data)
        except Exception:
            gone.append(ws)

    for ws in gone:
        dashboard_connections.discard(ws)


# ROUTES
@app.get("/")
async def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {
        "status": "running",
        "restaurant": "Zayqa",
        "currency": "PKR",
        "order_type": "dine-in",
        "gladia_configured": bool(GLADIA_API_KEY),
        "groq_configured": client_groq is not None
    }


@app.get("/api/menu")
async def menu_api():
    return get_menu()


@app.get("/api/orders")
async def orders_api():
    return get_all_orders()


class StatusUpdate(BaseModel):
    status: str = Field(
        pattern="^(New|Preparing|Ready|Completed|Cancelled)$"
    )


@app.patch("/api/orders/{order_id}/status")
async def update_order_status(order_id: int, body: StatusUpdate):
    with closing(get_db()) as c:
        if not c.execute(
            "SELECT id FROM orders WHERE id=?", (order_id,)
        ).fetchone():
            raise HTTPException(status_code=404, detail="Order not found")

        c.execute("""
            UPDATE orders
            SET status=?,updated_at=datetime('now','localtime')
            WHERE id=?
        """, (body.status, order_id))

        add_activity(
            c, order_id, f"Order status changed to {body.status}"
        )

        c.commit()
        order = get_order_details(c, order_id)

    await broadcast_update({
        "type": "order_updated",
        "order": order
    })

    return order


@app.websocket("/ws/dashboard")
async def dashboard_ws(ws: WebSocket):
    await ws.accept()
    dashboard_connections.add(ws)

    await ws.send_json({
        "type": "snapshot",
        "orders": get_all_orders(),
        "menu": get_menu()
    })

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        dashboard_connections.discard(ws)


# GROQ PARSER
def interpret_order(transcript, active_table):
    menu = [
        {"item_id": x["id"], "name": x["name"]}
        for x in get_menu()
    ]

    prompt = f"""
You parse restaurant waiter speech for Zayqa. Dine-in only.

Menu:
{json.dumps(menu, ensure_ascii=False)}

Current remembered table:
{active_table or "none"}

Return ONLY a JSON object with these keys:
intent, table_number, operations, notes, clarification.

Allowed intents:
order_update, table_only, clarification, other.

Operations must be an array. Each operation contains:
action (add/remove/set), item_id, quantity (integer).

Rules:
- Use exact menu item IDs from the provided menu.
- If speech gives a table but no item, use table_only.
- If an item is spoken without a table, use the remembered table.
- If no remembered table exists, ask for a table.
- If a table is spoken in the transcript, use that table.
- Never invent menu items or IDs.
- If an item is unclear, use clarification.
- For unrelated speech, use other.
- Do not treat fragments or noise as confirmed orders.
- Keep clarification short.
- Return valid JSON only.

Example:
{{"intent":"order_update","table_number":4,
"operations":[{{"action":"add","item_id":"FF002","quantity":1}}],
"notes":"","clarification":""}}
"""

    response = client_groq.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": transcript}
        ],
        temperature=0,
        max_completion_tokens=900,
        response_format={"type": "json_object"}
    )

    raw = response.choices[0].message.content or "{}"
    parsed = json.loads(raw)

    if not isinstance(parsed, dict):
        raise ValueError("Parser returned invalid JSON structure")

    return parsed


# TEXT TO SPEECH
async def generate_speech(text, source_text):
    urdu = any(
        "\u0600" <= ch <= "\u06ff"
        for ch in source_text
    )

    voice = "ur-PK-UzmaNeural" if urdu else "en-US-AriaNeural"

    stream = edge_tts.Communicate(text, voice)
    data = bytearray()

    async for part in stream.stream():
        if part["type"] == "audio":
            data.extend(part["data"])

    if not data:
        raise RuntimeError("No audio generated")

    return base64.b64encode(data).decode("ascii")


# HANDLE EACH INSTRUCTION
async def handle_instruction(ws, transcript, active_table):
    if not client_groq:
        await ws.send_json({
            "type": "error",
            "message": "Groq is not configured."
        })
        return

    try:
        parsed = await asyncio.to_thread(
            interpret_order,
            transcript,
            active_table["table_number"]
        )

        intent = parsed.get("intent")
        table = parsed.get("table_number") or active_table["table_number"]
        operations = parsed.get("operations") or []
        answer = ""

        if intent == "other":
            answer = (
                "I'm ready to help with a dine-in order. "
                "Please tell me the table and menu items."
            )

        elif intent == "table_only" and table:
            active_table["table_number"] = int(table)
            answer = (
                f"Table {table} noted. "
                "Please tell me the items for this order."
            )

        elif intent == "clarification" or not table or not operations:
            answer = parsed.get("clarification") or (
                "Please tell me the table number and menu items."
            )

        else:
            parsed["table_number"] = int(table)

            result, changes = await asyncio.to_thread(
                process_order_command, parsed
            )

            active_table["table_number"] = result["table_number"]

            await broadcast_update({
                "type": "order_updated",
                "order": result
            })

            answer = (
                f"Table {result['table_number']} updated. "
                f"{', '.join(changes)}. "
                f"Total is {result['total']:,} rupees."
            )

            await ws.send_json({
                "type": "assistant",
                "text": answer,
                "order": result,
                "table_number": result["table_number"]
            })

        if intent != "order_update" or not operations:
            await ws.send_json({
                "type": "assistant",
                "text": answer,
                "table_number": active_table["table_number"]
            })

        try:
            audio = await generate_speech(answer, transcript)

            await ws.send_json({
                "type": "audio",
                "audio": audio
            })

        except Exception:
            await ws.send_json({
                "type": "warning",
                "message": "Voice response could not be generated."
            })

    except Exception as e:
        print("Order parser/processing error:", repr(e))

        await ws.send_json({
            "type": "error",
            "message": (
                "I couldn't safely understand that. "
                "Please repeat the table and item clearly."
            )
        })


# GLADIA VOICE WEBSOCKET
@app.websocket("/ws/voice")
async def voice_ws(ws: WebSocket):
    await ws.accept()

    session = None
    ended = threading.Event()
    loop = asyncio.get_running_loop()

    active_table = {"table_number": None}
    lock = asyncio.Lock()

    async def send(data):
        try:
            await ws.send_json(data)
        except Exception:
            pass

    async def final_text(text):
        async with lock:
            await send({
                "type": "transcript",
                "text": text,
                "is_final": True
            })

            await handle_instruction(ws, text, active_table)

    try:
        while True:
            msg = await ws.receive()

            if msg.get("text") is not None:
                data = json.loads(msg["text"])

                if data.get("type") == "start":
                    if not GLADIA_API_KEY or not client_groq:
                        await send({
                            "type": "error",
                            "message": (
                                "Voice service is not configured. "
                                "Check your environment file."
                            )
                        })
                        continue

                    if session:
                        await send({
                            "type": "status",
                            "message": "Already connected."
                        })
                        continue

                    initial = data.get("table_number")

                    active_table["table_number"] = (
                        initial if isinstance(initial, int) else None
                    )

                    ended.clear()

                    config = {
                        "model": "solaria-1",
                        "encoding": "wav/pcm",
                        "sample_rate": 16000,
                        "bit_depth": 16,
                        "channels": 1,
                        "language_config": {
                            "languages": ["ur", "en"]
                        }
                    }

                    gladia = GladiaClient(
                        api_key=GLADIA_API_KEY,
                        api_url=GLADIA_API_URL
                    )

                    session = gladia.live_v2().start_session(
                        LiveV2InitRequest.from_dict(config)
                    )

                    @session.on("message")
                    def on_message(result):
                        if result.type != "transcript":
                            return

                        txt = result.data.utterance.text

                        if not txt:
                            return

                        if result.data.is_final:
                            asyncio.run_coroutine_threadsafe(
                                final_text(txt), loop
                            )

                    @session.on("error")
                    def on_error(error):
                        print("Gladia live-session error:", repr(error))

                        asyncio.run_coroutine_threadsafe(
                            send({
                                "type": "warning",
                                "message": (
                                    "Speech connection hiccup. "
                                    "Please try speaking again."
                                )
                            }),
                            loop
                        )

                    @session.once("ended")
                    def on_ended(_):
                        ended.set()

                    await send({
                        "type": "status",
                        "message": "Listening"
                    })

                elif data.get("type") == "stop":
                    if session:
                        try:
                            session.stop_recording()
                            await asyncio.to_thread(ended.wait, 5)
                        except Exception as e:
                            print("Gladia stop:", repr(e))

                        session = None

                    await send({
                        "type": "status",
                        "message": "Stopped"
                    })

                    break

            elif msg.get("bytes") is not None and session:
                try:
                    session.send_audio(msg["bytes"])

                except Exception as e:
                    print("Audio-send error:", repr(e))

                    await send({
                        "type": "warning",
                        "message": "Audio connection hiccup."
                    })

    except WebSocketDisconnect:
        print("Voice browser disconnected")

    except Exception as e:
        print("Voice session error:", repr(e))

        await send({
            "type": "error",
            "message": "Voice session couldn't connect. Please try again."
        })

    finally:
        if session:
            try:
                session.stop_recording()
            except Exception:
                pass