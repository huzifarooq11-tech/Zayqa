const $ = id => document.getElementById(id);

let orders = [];
let menuItems = [];
let currentFilter = "All";

let voiceSocket = null;
let dashboardSocket = null;

let mediaStream = null;
let audioContext = null;
let processorNode = null;
let sourceNode = null;
let muteGain = null;

let isListening = false;
let playbackBusy = false;
let audioQueue = [];

let rememberedTable =
    Number(localStorage.getItem("zayqa_table_number")) || null;


// MENU IMAGE LINKS
const imageByName = {
    "Chicken Biryani": "https://images.unsplash.com/photo-1563379091339-03246963d96a?auto=format&fit=crop&w=500&q=80",
    "Beef Biryani": "https://images.unsplash.com/photo-1563379091339-03246963d96a?auto=format&fit=crop&w=500&q=80",
    "Chicken Karahi": "https://images.unsplash.com/photo-1603894584373-5ac82b2ae398?auto=format&fit=crop&w=500&q=80",
    "Chicken Handi": "https://images.unsplash.com/photo-1603894584373-5ac82b2ae398?auto=format&fit=crop&w=500&q=80",
    "Seekh Kebab": "https://images.unsplash.com/photo-1599487488170-d11ec9c172f0?auto=format&fit=crop&w=500&q=80",
    "Chicken Tikka": "https://images.unsplash.com/photo-1599487488170-d11ec9c172f0?auto=format&fit=crop&w=500&q=80",
    "Chicken Chowmein": "https://images.unsplash.com/photo-1585032226651-759b368d7246?auto=format&fit=crop&w=500&q=80",
    "Chicken Manchurian": "https://images.unsplash.com/photo-1525755662778-989d0524087e?auto=format&fit=crop&w=500&q=80",
    "Egg Fried Rice": "https://images.unsplash.com/photo-1603133872878-684f208fb84b?auto=format&fit=crop&w=500&q=80",
    "Chicken Burger": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=500&q=80",
    "Zinger Burger": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=500&q=80",
    "French Fries": "https://images.unsplash.com/photo-1573080496219-bb080dd4f877?auto=format&fit=crop&w=500&q=80",
    "Cold Drink": "https://images.unsplash.com/photo-1544145945-f90425340c7e?auto=format&fit=crop&w=500&q=80",
    "Mineral Water": "https://images.unsplash.com/photo-1564419320461-6870880221ad?auto=format&fit=crop&w=500&q=80",
    "Fresh Lime": "https://images.unsplash.com/photo-1513558161293-cdaf765edfd7?auto=format&fit=crop&w=500&q=80",
    "Gulab Jamun": "https://images.unsplash.com/photo-1666190092159-9e3c6b9a2e20?auto=format&fit=crop&w=500&q=80"
};


// GENERAL
function money(v) {
    return "Rs " + Number(v || 0).toLocaleString("en-PK");
}

function logActivity(title, detail = "") {
    if (!$("activityLog")) return;

    const row = document.createElement("div");
    row.className = "log-item";

    row.innerHTML = `
        <span class="log-dot"></span>
        <div>
            <strong></strong>
            <small></small>
        </div>
    `;

    row.querySelector("strong").textContent = title;

    row.querySelector("small").textContent =
        detail || new Date().toLocaleTimeString();

    $("activityLog").prepend(row);

    while ($("activityLog").children.length > 25) {
        $("activityLog").lastChild.remove();
    }
}

function addConversation(text, role) {
    const box = $("conversation");

    if (!box) return;

    box.querySelector(".conversation-empty")?.remove();

    const element = document.createElement("div");
    element.className = `chat-msg ${role}`;
    element.textContent = text;

    box.append(element);
    box.scrollTop = box.scrollHeight;
}

function setVoiceState(text, connected) {
    if ($("voiceStatus")) {
        $("voiceStatus").lastElementChild.textContent = text;
    }

    $("voiceStatus")?.classList.toggle("connected", connected);

    $("voiceVisual")?.classList.toggle(
        "active",
        connected && isListening
    );

    if ($("startBtn")) $("startBtn").disabled = connected;
    if ($("stopBtn")) $("stopBtn").disabled = !connected;
}


// DASHBOARD STATISTICS
function renderStats() {
    const active = orders.filter(o =>
        ["New", "Preparing", "Ready"].includes(o.status)
    );

    $("activeCount").textContent = active.length;

    $("newCount").textContent =
        orders.filter(o => o.status === "New").length;

    $("readyCount").textContent =
        orders.filter(o => o.status === "Ready").length;

    $("revenueValue").textContent =
        money(active.reduce((s, o) => s + o.total, 0));

    $("navOrderCount").textContent = active.length;

    $("orderCountLabel").textContent =
        `${orders.length} orders`;
}


// RENDER ORDERS
function renderOrders() {
    renderStats();

    const list = $("ordersList");
    list.replaceChildren();

    const shown = orders.filter(o =>
        currentFilter === "All" || o.status === currentFilter
    );

    if (!shown.length) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">▤</div>
                <strong>No matching orders</strong>
                <p>Orders will appear here as soon as they are created.</p>
            </div>
        `;

        return;
    }

    shown.forEach(o => {
        const card = document.createElement("article");
        card.className = "order-card";

        const head = document.createElement("div");
        head.className = "order-head";

        head.innerHTML = `
            <div>
                <div class="table-title"></div>
                <div class="order-meta"></div>
            </div>
            <span class="status"></span>
        `;

        head.querySelector(".table-title").textContent =
            `Table ${o.table_number} · #${o.id}`;

        head.querySelector(".order-meta").textContent =
            `Dine-in · ${o.created_at}`;

        const status = head.querySelector(".status");

        status.className =
            `status status-${o.status.toLowerCase()}`;

        status.textContent = o.status;

        card.append(head);

        const lines = document.createElement("div");
        lines.className = "order-lines";

        (o.items || []).forEach(item => {
            const line = document.createElement("div");
            line.className = "order-line";

            line.innerHTML = "<span></span><span></span>";

            line.children[0].textContent =
                `${item.quantity} × ${item.name}`;

            line.children[1].textContent =
                money(item.line_total);

            lines.append(line);
        });

        card.append(lines);

        const total = document.createElement("div");
        total.className = "order-total";

        total.innerHTML = "<span>Order total</span><span></span>";

        total.lastElementChild.textContent = money(o.total);

        card.append(total);

        const actions = document.createElement("div");
        actions.className = "order-actions";

        ["New", "Preparing", "Ready", "Completed"]
            .filter(s => s !== o.status)
            .forEach(s => {
                const button = document.createElement("button");

                button.textContent =
                    s === "Preparing"
                    ? "Start preparing"
                    : s === "Completed"
                    ? "Complete"
                    : `Mark ${s.toLowerCase()}`;

                button.onclick = () => changeStatus(o.id, s);

                actions.append(button);
            });

        card.append(actions);
        list.append(card);
    });
}


// MENU WITH PICTURES
function renderMenu() {
    if (!$("menuGrid")) return;

    $("menuCount").textContent =
        `${menuItems.length} items`;

    const grid = $("menuGrid");
    grid.replaceChildren();

    menuItems.forEach(item => {
        const card = document.createElement("div");
        card.className = "menu-item";

        const img = document.createElement("img");
        img.className = "menu-photo";
        img.loading = "lazy";
        img.alt = item.name;

        img.src = imageByName[item.name] ||
            "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=500&q=80";

        img.onerror = () => {
            img.src =
                "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=500&q=80";
        };

        const category = document.createElement("div");
        category.className = "menu-category";
        category.textContent = item.category;

        const name = document.createElement("div");
        name.className = "menu-name";
        name.textContent = item.name;

        const price = document.createElement("div");
        price.className = "menu-price";
        price.textContent = money(item.price);

        const desc = document.createElement("div");
        desc.className = "menu-desc";
        desc.textContent = item.description || "";

        card.append(img, category, name, price, desc);
        grid.append(card);
    });
}


// LOAD DATA
async function loadInitial() {
    const [a, b] = await Promise.all([
        fetch("/api/orders"),
        fetch("/api/menu")
    ]);

    if (!a.ok || !b.ok) {
        throw Error("Could not load dashboard data");
    }

    orders = await a.json();
    menuItems = await b.json();

    renderOrders();
    renderMenu();
}


// STATUS UPDATE
async function changeStatus(id, status) {
    try {
        const response = await fetch(
            `/api/orders/${id}/status`,
            {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ status })
            }
        );

        if (!response.ok) throw Error();

        upsertOrder(await response.json());

        logActivity(`Order #${id} marked ${status}`);

    } catch {
        logActivity("Status update failed");
    }
}


// INSERT / UPDATE ORDER
function upsertOrder(o) {
    const i = orders.findIndex(x => x.id === o.id);

    if (i >= 0) orders[i] = o;
    else orders.unshift(o);

    orders.sort((a, b) => b.id - a.id);

    renderOrders();
}


// DASHBOARD SOCKET
function connectDashboard() {
    const p = location.protocol === "https:" ? "wss" : "ws";

    dashboardSocket = new WebSocket(
        `${p}://${location.host}/ws/dashboard`
    );

    dashboardSocket.onmessage = e => {
        const d = JSON.parse(e.data);

        if (d.type === "snapshot") {
            orders = d.orders || [];
            menuItems = d.menu || [];

            renderOrders();
            renderMenu();
        }

        if (d.type === "order_updated") {
            upsertOrder(d.order);
        }
    };

    dashboardSocket.onclose = () => {
        setTimeout(connectDashboard, 2500);
    };
}


// AUDIO PLAYBACK
function playNextAudio() {
    if (playbackBusy || !audioQueue.length || !audioContext) {
        return;
    }

    playbackBusy = true;

    const b64 = audioQueue.shift();
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);

    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }

    audioContext.decodeAudioData(bytes.buffer)
        .then(buffer => {
            const src = audioContext.createBufferSource();
            src.buffer = buffer;
            src.connect(audioContext.destination);

            src.onended = () => {
                playbackBusy = false;
                playNextAudio();
            };

            src.start();
        })
        .catch(() => {
            playbackBusy = false;
            playNextAudio();
        });
}

function queueAudio(a) {
    audioQueue.push(a);
    playNextAudio();
}


// VOICE SOCKET
function connectVoiceSocket() {
    return new Promise((resolve, reject) => {
        const p = location.protocol === "https:" ? "wss" : "ws";

        voiceSocket = new WebSocket(
            `${p}://${location.host}/ws/voice`
        );

        voiceSocket.binaryType = "arraybuffer";

        voiceSocket.onopen = resolve;

        voiceSocket.onerror = () =>
            reject(Error("Voice server connection failed"));

        voiceSocket.onmessage = e => {
            const d = JSON.parse(e.data);

            if (d.type === "status") {
                setVoiceState(d.message, true);
            }

            if (d.type === "transcript" && d.is_final) {
                addConversation(d.text, "waiter");
            }

            if (d.type === "assistant") {
                addConversation(d.text, "assistant");

                if (Number.isInteger(d.table_number)) {
                    rememberedTable = d.table_number;

                    localStorage.setItem(
                        "zayqa_table_number",
                        rememberedTable
                    );
                }

                if (d.order) {
                    rememberedTable = d.order.table_number;

                    localStorage.setItem(
                        "zayqa_table_number",
                        rememberedTable
                    );

                    upsertOrder(d.order);
                }
            }

            if (d.type === "audio") {
                queueAudio(d.audio);
            }

            if (d.type === "error") {
                addConversation(d.message, "assistant");
                logActivity("Voice processing issue");
            }

            if (d.type === "warning") {
                // Technical connection warnings are kept out of the UI.
            }
        };

        voiceSocket.onclose = () => {
            if (isListening) cleanupVoice(false);
        };
    });
}


// START CONVERSATION
async function startConversation() {
    try {
        $("startBtn").disabled = true;

        if (!navigator.mediaDevices?.getUserMedia) {
            throw Error("Microphone access requires localhost or HTTPS");
        }

        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });

        audioContext = new (
            window.AudioContext || window.webkitAudioContext
        )({
            sampleRate: 16000
        });

        await audioContext.resume();

        await connectVoiceSocket();

        voiceSocket.send(JSON.stringify({
            type: "start",
            table_number: rememberedTable
        }));

        await audioContext.audioWorklet.addModule(
            "/static/audio-processor.js"
        );

        sourceNode =
            audioContext.createMediaStreamSource(mediaStream);

        processorNode = new AudioWorkletNode(
            audioContext,
            "pcm-processor"
        );

        muteGain = audioContext.createGain();
        muteGain.gain.value = 0;

        processorNode.port.onmessage = e => {
            if (
                voiceSocket &&
                voiceSocket.readyState === WebSocket.OPEN &&
                isListening
            ) {
                voiceSocket.send(e.data);
            }
        };

        sourceNode.connect(processorNode);
        processorNode.connect(muteGain);
        muteGain.connect(audioContext.destination);

        isListening = true;

        setVoiceState("Connected · Listening", true);

        $("voiceVisual").classList.add("active");

        logActivity("Voice assistant connected");

    } catch (e) {
        logActivity("Could not start voice session");

        cleanupVoice(false);

        $("startBtn").disabled = false;
    }
}


// STOP / CLEANUP
function cleanupVoice(sendStop = true) {
    isListening = false;

    $("voiceVisual")?.classList.remove("active");

    if (
        sendStop &&
        voiceSocket &&
        voiceSocket.readyState === WebSocket.OPEN
    ) {
        try {
            voiceSocket.send(JSON.stringify({ type: "stop" }));
        } catch {}
    }

    if (processorNode) {
        processorNode.disconnect();
        processorNode = null;
    }

    if (sourceNode) {
        sourceNode.disconnect();
        sourceNode = null;
    }

    if (muteGain) {
        muteGain.disconnect();
        muteGain = null;
    }

    if (mediaStream) {
        mediaStream.getTracks().forEach(t => t.stop());
        mediaStream = null;
    }

    if (audioContext) {
        audioContext.close().catch(() => {});
        audioContext = null;
    }

    if (voiceSocket) {
        voiceSocket.close();
        voiceSocket = null;
    }

    audioQueue = [];
    playbackBusy = false;

    setVoiceState("Not connected", false);

    if ($("startBtn")) $("startBtn").disabled = false;
}


// BUTTONS
$("startBtn")?.addEventListener("click", startConversation);

$("stopBtn")?.addEventListener("click", () => {
    cleanupVoice(true);
    logActivity("Voice session stopped");
});

$("refreshBtn")?.addEventListener("click", () => {
    loadInitial()
        .then(() => logActivity("Dashboard refreshed"))
        .catch(() => logActivity("Refresh failed"));
});

$("clearLogBtn")?.addEventListener("click", () => {
    $("activityLog").replaceChildren();
});


// FILTERS
document.querySelectorAll(".filter").forEach(b => {
    b.addEventListener("click", () => {
        document.querySelectorAll(".filter").forEach(x =>
            x.classList.remove("active")
        );

        b.classList.add("active");

        currentFilter = b.dataset.filter;

        renderOrders();
    });
});


// INITIALIZE
if ($("todayLabel")) {
    $("todayLabel").textContent =
        new Date().toLocaleDateString("en-PK", {
            weekday: "short",
            day: "numeric",
            month: "short",
            year: "numeric"
        });
}

loadInitial()
    .then(() => {
        logActivity("Zayqa dashboard ready");
        connectDashboard();
    })
    .catch(() => logActivity("Dashboard data could not load"));