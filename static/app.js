"use strict";
/* ===========================================================================
   Drive Chatbot — 채팅 클라이언트 (9단계)
   구조: 상태 → DOM refs → API 헬퍼 → 유틸 → 렌더 → 액션 → 이벤트
   API 응답 모양(app/models/chat.py):
     ChatResponse  {room_id, message_id, answer, sources[{title,uri,score}], ...}
     RoomItem      {room_id, title, created_at, updated_at}
     MessageItem   {message_id, role, content, sources|null, feedback|null, created_at}
   주의: 채팅 응답은 'answer', 메시지 항목은 'content' → 전송 후 매핑해서 렌더.
   =========================================================================== */

// ===== 상태 =====
let currentRoomId = null;
let rooms = [];          // 사이드바 캐시 (제목 조회용)
let sending = false;     // 중복 전송 방지

// ===== DOM refs =====
const el = {
  userInfo:   document.getElementById("user-info"),
  roomList:   document.getElementById("room-list"),
  newChatBtn: document.getElementById("new-chat-btn"),
  roomTitle:  document.getElementById("room-title"),
  messages:   document.getElementById("messages"),
  loading:    document.getElementById("loading"),
  form:       document.getElementById("chat-form"),
  input:      document.getElementById("query-input"),
  sendBtn:    document.getElementById("send-btn"),
  hamburger:  document.getElementById("hamburger"),
  sidebar:    document.getElementById("sidebar"),
  overlay:    document.getElementById("sidebar-overlay"),
};

// 서버가 렌더한 빈 화면(추천 질문 칩 포함)을 그대로 보관 → '새 대화' 때 복원
const EMPTY_STATE_HTML = el.messages.innerHTML;

// ===========================================================================
// API 헬퍼
//   - credentials:"include" → 세션 쿠키 전달 (빠지면 401 무한루프)
//   - redirect:"manual"     → 세션 만료 시 서버의 302(/login)를 fetch 가 따라가
//                             HTML 을 받아 깨지는 문제 방지. opaqueredirect 로 감지.
// ===========================================================================
async function apiGet(path) {
  return handle(await fetch(path, { credentials: "include", redirect: "manual" }));
}
async function apiPost(path, body) {
  return handle(await fetch(path, {
    method: "POST",
    credentials: "include",
    redirect: "manual",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  }));
}
async function handle(res) {
  // 세션 만료로 인한 페이지 리다이렉트(302) 또는 API 미인증(401) → 로그인으로
  if (res.type === "opaqueredirect" || res.status === 0 || res.status === 401) {
    window.location.href = "/login";
    throw new Error("unauthorized");
  }
  if (res.status === 429) {
    alert("요청이 너무 잦아요. 1분에 5회까지 가능합니다. 잠시 후 다시 시도해주세요.");
    throw new Error("rate_limited");
  }
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail || ""; } catch (_) { /* noop */ }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ===== 유틸 =====
// XSS 방어: 사용자/AI 텍스트는 반드시 이걸 거친 뒤 innerHTML 에 넣는다.
// 줄바꿈(\n)은 <br> 주입 대신 CSS white-space:pre-wrap 으로 표현(더 안전).
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
// DOM 그린 뒤 스크롤(메시지 추가 직후 바로 하면 높이가 안 잡힘)
function scrollToBottom() {
  requestAnimationFrame(() => { el.messages.scrollTop = el.messages.scrollHeight; });
}
function hideEmptyState() {
  const es = document.getElementById("empty-state");
  if (es) es.remove();
}

// ===========================================================================
// 렌더링
// ===========================================================================
function renderRooms() {
  el.roomList.innerHTML = "";
  rooms.forEach((r) => {
    const li = document.createElement("li");
    li.className = "room-item" + (r.room_id === currentRoomId ? " active" : "");
    li.textContent = r.title || "새 대화";
    li.title = r.title || "";
    li.addEventListener("click", () => loadRoom(r.room_id));
    el.roomList.appendChild(li);
  });
}

function renderMessage(m) {
  hideEmptyState();

  const wrap = document.createElement("div");
  wrap.className = "msg " + (m.role === "user" ? "user" : "assistant");

  const content = document.createElement("div");
  content.className = "msg-content";
  content.innerHTML = escapeHtml(m.content);   // escape 후 삽입
  wrap.appendChild(content);

  if (m.role === "assistant" && Array.isArray(m.sources) && m.sources.length) {
    wrap.appendChild(renderSources(m.sources));
  }
  if (m.role === "assistant" && m.message_id) {
    wrap.appendChild(renderFeedback(m));
  }

  el.messages.appendChild(wrap);
  return wrap;
}

function renderSources(sources) {
  const box = document.createElement("div");
  box.className = "sources";
  sources.forEach((s) => {
    const a = document.createElement("a");
    a.className = "source-btn";
    a.href = s.uri;
    a.target = "_blank";
    a.rel = "noopener noreferrer";        // 탭 하이재킹 방어
    a.innerHTML =
      `<span class="label">${escapeHtml(s.title || s.uri)}</span>` +
      `<span class="ext-icon" aria-hidden="true">↗</span>`;
    box.appendChild(a);
  });
  return box;
}

function renderFeedback(m) {
  const fb = document.createElement("div");
  fb.className = "feedback";
  [["up", "👍"], ["down", "👎"]].forEach(([value, emoji]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "feedback-btn" + (m.feedback === value ? " active" : "");
    b.textContent = emoji;
    b.setAttribute("aria-label", value === "up" ? "도움이 됐어요" : "아쉬워요");
    b.addEventListener("click", () => submitFeedback(m.message_id, value, fb));
    fb.appendChild(b);
  });
  return fb;
}

// ===========================================================================
// 액션
// ===========================================================================
async function init() {
  try {
    const me = await apiGet("/me");
    el.userInfo.textContent = me.email || me.user_email || "";
  } catch (_) {
    return; // 미인증이면 handle()이 이미 /login 으로 보냄
  }
  await loadRooms();
}

async function loadRooms() {
  try {
    const data = await apiGet("/api/rooms");
    // updated_at 최신순 정렬 (최근 대화가 위로). 값은 ISO 문자열이라 문자열 비교로 충분.
    rooms = (data || []).slice().sort(
      (a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || ""))
    );
    renderRooms();
  } catch (_) { /* handle()에서 처리됨 */ }
}

async function loadRoom(roomId) {
  currentRoomId = roomId;
  const room = rooms.find((r) => r.room_id === roomId);
  el.roomTitle.textContent = (room && room.title) || "대화";
  renderRooms();                       // active 강조 갱신
  closeSidebar();                      // 모바일: 방 선택하면 사이드바 닫기
  try {
    const msgs = await apiGet(`/api/rooms/${roomId}/messages`);
    el.messages.innerHTML = "";
    (msgs || []).forEach(renderMessage);
  } catch (_) {
    el.messages.innerHTML = "";
  }
  scrollToBottom();
}

function newChat() {
  currentRoomId = null;
  el.roomTitle.textContent = "새 대화";
  el.messages.innerHTML = EMPTY_STATE_HTML;   // 추천 질문 칩 복원
  renderRooms();                              // active 해제
  closeSidebar();                             // 모바일: 사이드바 닫기
  el.input.focus();
}

// ===========================================================================
// 모바일 사이드바 (햄버거)
//   데스크탑은 CSS 미디어쿼리상 off-canvas 가 아니라 이 토글이 무해(영향 없음).
// ===========================================================================
function openSidebar() {
  el.sidebar.classList.add("open");
  el.overlay.classList.add("show");
}
function closeSidebar() {
  el.sidebar.classList.remove("open");
  el.overlay.classList.remove("show");
}

async function sendMessage(query) {
  if (!query || sending) return;
  sending = true;
  el.sendBtn.disabled = true;

  // 낙관적 UI: 보낸 메시지를 즉시 표시
  hideEmptyState();
  renderMessage({ role: "user", content: query });
  scrollToBottom();
  el.input.value = "";
  el.input.style.height = "auto";
  el.loading.hidden = false;

  try {
    const resp = await apiPost("/api/chat", { query, room_id: currentRoomId });
    currentRoomId = resp.room_id;
    // ChatResponse(answer) → MessageItem 모양(content) 으로 매핑해서 렌더
    renderMessage({
      message_id: resp.message_id,
      role: "assistant",
      content: resp.answer,
      sources: resp.sources,
      feedback: null,
    });
    scrollToBottom();
    await loadRooms();                  // 사이드바 갱신(신규 방 표시/정렬). 메시지 영역은 유지.
  } catch (err) {
    // 401/429 는 handle()에서 이미 처리 → 그 외 오류만 인라인 안내
    if (err && err.message !== "unauthorized" && err.message !== "rate_limited") {
      renderMessage({
        role: "assistant",
        content: "⚠️ 답변을 생성하지 못했어요. 잠시 후 다시 시도해주세요.",
      });
      scrollToBottom();
    }
  } finally {
    el.loading.hidden = true;
    el.sendBtn.disabled = false;
    sending = false;
    el.input.focus();
  }
}

// 피드백: 즉시 반영(낙관적) + 서버 저장. FeedbackRequest 는 up|down 만 허용(해제 불가).
// 저장 실패 시에만 방을 다시 읽어 실제 상태로 되돌림.
async function submitFeedback(messageId, value, fbEl) {
  if (!currentRoomId) return;
  if (fbEl) {
    const want = value === "up" ? "👍" : "👎";
    [...fbEl.children].forEach((btn) => btn.classList.toggle("active", btn.textContent === want));
  }
  try {
    await apiPost(`/api/rooms/${currentRoomId}/messages/${messageId}/feedback`, { feedback: value });
  } catch (_) {
    await loadRoom(currentRoomId);
  }
}

// ===========================================================================
// 이벤트
// ===========================================================================
el.form.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(el.input.value.trim());
});

// Enter = 전송, Shift+Enter = 줄바꿈
el.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    el.form.requestSubmit();
  }
});

// textarea 자동 높이
el.input.addEventListener("input", () => {
  el.input.style.height = "auto";
  el.input.style.height = Math.min(el.input.scrollHeight, 160) + "px";
});

el.newChatBtn.addEventListener("click", newChat);

// 모바일 사이드바 토글
el.hamburger.addEventListener("click", openSidebar);
el.overlay.addEventListener("click", closeSidebar);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSidebar(); });

// 추천 질문 칩(이벤트 위임 → innerHTML 교체에도 살아남음)
el.messages.addEventListener("click", (e) => {
  const chip = e.target.closest(".suggestion-chip");
  if (!chip) return;
  el.input.value = chip.dataset.q || chip.textContent;
  el.form.requestSubmit();
});

// ===== 시작 =====
init();
