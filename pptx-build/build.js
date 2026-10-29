const pptxgen = require("pptxgenjs");
const path = require("path");

const THEME = {
  name: "Housing Bot",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "15223D",
    lt1: "FFFFFF",
    dk2: "1B3A6B",
    lt2: "E9EEF6",
    accent1: "C9A876",
    accent2: "3E6AA6",
    accent3: "7BA7D9",
    accent4: "2F8F7C",
    accent5: "8C98AC",
    accent6: "9C7A3C",
    hlink: "C9A876",
    folHlink: "9C7A3C",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };

const C = pres.SchemeColor;
const ASSET = (f) => path.join(__dirname, "assets", f);

const PAGE_W = 13.333;
const PAGE_H = 7.5;
const MARGIN = 0.6;

// ---------- Layouts ----------

pres.defineSlideMaster({
  title: "TITLE_SLIDE",
  background: { color: THEME.colors.dk1 },
  objects: [
    { placeholder: {
        options: { name: "title", type: "title", x: 0.9, y: 2.55, w: 11.5, h: 1.5,
          fontFace: THEME.headFontFace, fontSize: 40, bold: true, color: THEME.colors.lt1, align: "left" },
        text: "",
      } },
    { placeholder: {
        options: { name: "subtitle", type: "body", x: 0.9, y: 4.05, w: 10.5, h: 0.9,
          fontFace: THEME.bodyFontFace, fontSize: 18, color: THEME.colors.accent3, align: "left" },
        text: "",
      } },
  ],
});

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: THEME.colors.lt1 },
  objects: [
    { placeholder: {
        options: { name: "title", type: "title", x: MARGIN, y: 0.45, w: PAGE_W - 2 * MARGIN, h: 0.8,
          fontFace: THEME.headFontFace, fontSize: 30, bold: true, color: THEME.colors.dk2, align: "left" },
        text: "",
      } },
    { text: { text: "Housing Bank · AI Chatbot", options: {
          x: PAGE_W - 3.6, y: 7.08, w: 3.0, h: 0.3, fontFace: THEME.bodyFontFace, fontSize: 9,
          color: THEME.colors.accent5, align: "right", margin: 0,
        } } },
    { text: { text: "", options: { x: 0, y: 7.08, w: 0.1, h: 0.1 } } },
  ],
  slideNumber: { x: MARGIN, y: 7.08, fontFace: THEME.bodyFontFace, fontSize: 9, color: THEME.colors.accent5 },
});

pres.defineSlideMaster({
  title: "CLOSING",
  background: { color: THEME.colors.dk2 },
  objects: [
    { placeholder: {
        options: { name: "title", type: "title", x: 0.9, y: 2.7, w: 11.5, h: 1.3,
          fontFace: THEME.headFontFace, fontSize: 34, bold: true, color: THEME.colors.lt1, align: "left" },
        text: "",
      } },
  ],
});

// ---------- Helpers ----------

function iconCircle(slide, { x, y, d = 0.5, fill, glyph, glyphColor = THEME.colors.lt1, fontSize = 18 }) {
  slide.addShape(pres.ShapeType.ellipse, { x, y, w: d, h: d, fill: { color: fill }, line: { type: "none" } });
  slide.addText(glyph, {
    x, y, w: d, h: d, align: "center", valign: "middle",
    fontFace: THEME.bodyFontFace, fontSize, color: glyphColor, bold: true, margin: 0, isTextBox: true,
  });
}

function browserFrame(slide, { imgPath, x, y, w, barColor = THEME.colors.accent5, shadow = true }) {
  // screenshots are 1366x633 ≈ 2.158:1
  const h = w / (1366 / 633);
  const barH = 0.22;
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h: h + barH, rectRadius: 0.06,
    fill: { color: "F3F4F6" }, line: { color: "D9DCE3", width: 0.75 },
    shadow: shadow ? { type: "outer", color: "1B2437", opacity: 0.22, blur: 10, offset: 3, angle: 90 } : undefined,
  });
  [0, 1, 2].forEach((i) => {
    slide.addShape(pres.ShapeType.ellipse, {
      x: x + 0.12 + i * 0.16, y: y + barH / 2 - 0.035, w: 0.07, h: 0.07,
      fill: { color: ["E0645A", "E8B04B", "4CAF7D"][i] }, line: { type: "none" },
    });
  });
  slide.addImage({ path: imgPath, x, y: y + barH, w, h });
}

function bulletList(slide, items, { x, y, w, fontSize = 14, color = THEME.colors.dk1, gap = 10 }) {
  slide.addText(
    items.map((t, i) => ({
      text: t,
      options: { bullet: { code: "2022", indent: 18 }, breakLine: i !== items.length - 1 },
    })),
    {
      x, y, w, h: 4,
      fontFace: THEME.bodyFontFace, fontSize, color, align: "left", valign: "top",
      paraSpaceAfter: gap, margin: 0, isTextBox: true,
    },
  );
}

// ================= Slide 1: Title =================
{
  const s = pres.addSlide({ masterName: "TITLE_SLIDE" });
  iconCircle(s, { x: 0.9, y: 1.5, d: 0.62, fill: THEME.colors.accent1, glyph: "✨", fontSize: 22 });
  s.addText("HOUSING BOT", {
    x: 1.68, y: 1.5, w: 6, h: 0.62, valign: "middle",
    fontFace: THEME.bodyFontFace, fontSize: 13, color: THEME.colors.accent1, bold: true, charSpacing: 3,
    margin: 0, isTextBox: true,
  });
  s.addText("Housing Bank's AI Chatbot", { placeholder: "title" });
  s.addText(
    "A feature walkthrough — admin tools, member experience, and how every answer is generated strictly from your own uploaded documents.",
    { placeholder: "subtitle" },
  );
  s.addShape(pres.ShapeType.line, {
    x: 0.9, y: 6.6, w: 11.5, h: 0, line: { color: THEME.colors.dk2, width: 1 },
  });
  s.addText("Prepared for internal review", {
    x: 0.9, y: 6.75, w: 8, h: 0.4, fontFace: THEME.bodyFontFace, fontSize: 11,
    color: THEME.colors.accent5, margin: 0, isTextBox: true,
  });
}

// ================= Slide 2: Two roles overview =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Two ways people use Housing Bot", { placeholder: "title" });
  s.addText("Every tenant account has two role types, each with a purpose-built interface.", {
    x: MARGIN, y: 1.25, w: 11, h: 0.4, fontFace: THEME.bodyFontFace, fontSize: 13,
    color: THEME.colors.accent5, margin: 0, isTextBox: true,
  });

  const cardY = 2.0, cardW = 5.65, cardH = 4.5, gap = 0.4;
  const cards = [
    {
      x: MARGIN, fill: THEME.colors.dk2, accent: THEME.colors.accent1,
      kicker: "ADMIN", title: "Manages the knowledge the bot uses",
      items: [
        "Uploads and organizes documents (Knowledge Base)",
        "Adds and manages company users",
        "Reviews conversation history and analytics",
        "Handles support tickets raised by members",
        "Housing Bank only: manages the Index and Ask AI file sets",
      ],
    },
    {
      x: MARGIN + cardW + gap, fill: THEME.colors.lt2, accent: THEME.colors.dk2,
      kicker: "MEMBER", title: "Asks questions and gets answers",
      items: [
        "Asks the chatbot questions by text or voice",
        "Browses the FAQ",
        "Housing Bank only: searches the Index (keyword search)",
        "Housing Bank only: uses Ask AI (AI-generated answers)",
        "No access to document uploads or other users' data",
      ],
      dark: false,
    },
  ];

  cards.forEach((c) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: c.x, y: cardY, w: cardW, h: cardH, rectRadius: 0.08,
      fill: { color: c.fill }, line: { type: "none" },
      shadow: { type: "outer", color: "1B2437", opacity: 0.18, blur: 12, offset: 3, angle: 90 },
    });
    s.addText(c.kicker, {
      x: c.x + 0.4, y: cardY + 0.32, w: cardW - 0.8, h: 0.3,
      fontFace: THEME.bodyFontFace, fontSize: 11, bold: true, color: c.accent, charSpacing: 2,
      margin: 0, isTextBox: true,
    });
    s.addText(c.title, {
      x: c.x + 0.4, y: cardY + 0.62, w: cardW - 0.8, h: 0.8,
      fontFace: THEME.headFontFace, fontSize: 19, bold: true,
      color: c.dark === false ? THEME.colors.dk1 : THEME.colors.lt1,
      margin: 0, isTextBox: true,
    });
    bulletList(s, c.items, {
      x: c.x + 0.4, y: cardY + 1.55, w: cardW - 0.8, fontSize: 13,
      color: c.dark === false ? THEME.colors.dk1 : THEME.colors.lt1, gap: 12,
    });
  });
}

// ================= Slide 3: Admin dashboard =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("The admin dashboard", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("admin-nav.jpg"), x: MARGIN, y: 1.35, w: 7.3 });
  bulletList(
    s,
    [
      "Knowledge Base — upload the documents the bot answers from",
      "Users — add and manage company accounts",
      "Conversations — review what members have asked",
      "Analytics — usage and performance over time",
      "Support Tickets — answer questions the bot couldn't",
      "Index & Ask AI — Housing Bank's own search tools (next slides)",
    ],
    { x: 8.1, y: 1.6, w: 4.6, fontSize: 13, gap: 14 },
  );
}

// ================= Slide 4: Admin - Users =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Admin: managing company users", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("admin-users.jpg"), x: MARGIN, y: 1.35, w: 7.3 });
  bulletList(
    s,
    [
      "Add users one at a time, or import a list from Excel",
      "Two roles available: Admin (full access) and Member (chat + FAQ only)",
      "Each user signs in with their own email and password",
      "Admins can remove access at any time",
    ],
    { x: 8.1, y: 1.6, w: 4.6, fontSize: 13, gap: 14 },
  );
}

// ================= Slide 5: Member experience =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("The member experience", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("member-nav.jpg"), x: MARGIN, y: 1.35, w: 7.3 });
  bulletList(
    s,
    [
      "A simpler top bar instead of the admin sidebar",
      "Bot — the main chat",
      "FAQ — common questions, answered in advance",
      "Index — keyword search across indexed files",
      "Ask AI — AI-generated answers from indexed files",
      "No visibility into other users, uploads, or settings",
    ],
    { x: 8.1, y: 1.6, w: 4.6, fontSize: 13, gap: 13 },
  );
}

// ================= Slide 6: How answers are generated =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Every answer comes from your own documents", { placeholder: "title" });
  s.addText(
    "The chatbot does not answer from general knowledge. It searches the documents your team uploaded, " +
      "then writes a natural-language answer using only what it finds there — and says so plainly when it finds nothing relevant.",
    {
      x: MARGIN, y: 1.25, w: 11.9, h: 0.6, fontFace: THEME.bodyFontFace, fontSize: 13,
      color: THEME.colors.accent5, margin: 0, isTextBox: true,
    },
  );

  const steps = [
    { n: "1", t: "Upload", d: "Your slides and documents are added to the Knowledge Base." },
    { n: "2", t: "Search", d: "A question searches that content for the genuinely relevant passages." },
    { n: "3", t: "Answer", d: "The AI writes a clear answer using only those passages — in the question's own language." },
  ];
  const stepW = 3.7, stepGap = 0.25, startX = MARGIN;
  steps.forEach((st, i) => {
    const x = startX + i * (stepW + stepGap);
    s.addShape(pres.ShapeType.roundRect, {
      x, y: 2.05, w: stepW, h: 1.5, rectRadius: 0.08,
      fill: { color: THEME.colors.lt2 }, line: { type: "none" },
    });
    iconCircle(s, { x: x + 0.3, y: 2.3, d: 0.5, fill: THEME.colors.dk2, glyph: st.n, fontSize: 18, glyphColor: THEME.colors.lt1 });
    s.addText(st.t, {
      x: x + 0.95, y: 2.28, w: stepW - 1.2, h: 0.35, fontFace: THEME.headFontFace, fontSize: 15, bold: true,
      color: THEME.colors.dk2, margin: 0, isTextBox: true,
    });
    s.addText(st.d, {
      x: x + 0.3, y: 2.88, w: stepW - 0.6, h: 0.6, fontFace: THEME.bodyFontFace, fontSize: 11.5,
      color: THEME.colors.dk1, margin: 0, isTextBox: true,
    });
  });

  s.addText("Live example — English", {
    x: MARGIN, y: 3.8, w: 6, h: 0.3, fontFace: THEME.bodyFontFace, fontSize: 12, bold: true,
    color: THEME.colors.accent6, margin: 0, isTextBox: true,
  });
  browserFrame(s, { imgPath: ASSET("chat-en.jpg"), x: MARGIN, y: 4.1, w: 5.5 });
  s.addText(
    "The question matched a slide titled “Payment or Delivery Terms of the Bills for Collection,” " +
      "so the answer reflects that content directly — including every step the slide lists.",
    {
      x: MARGIN + 5.5 + 0.4, y: 4.25, w: 5.4, h: 2.5, fontFace: THEME.bodyFontFace, fontSize: 13,
      italic: true, color: THEME.colors.dk1, valign: "top", margin: 0, isTextBox: true,
    },
  );
}

// ================= Slide 7: Arabic example =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Bilingual by default", { placeholder: "title" });
  s.addText(
    "The same question, answered in Arabic — the AI matches the language of the question, " +
      "even when the source document is in English.",
    {
      x: MARGIN, y: 1.25, w: 11.9, h: 0.5, fontFace: THEME.bodyFontFace, fontSize: 13,
      color: THEME.colors.accent5, margin: 0, isTextBox: true,
    },
  );
  browserFrame(s, { imgPath: ASSET("chat-ar.jpg"), x: 1.9, y: 2.05, w: 9.5 });
}

// ================= Slide 8: Index feature =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Index: fast keyword search", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("index-page.jpg"), x: MARGIN, y: 1.35, w: 7.3 });
  bulletList(
    s,
    [
      "A separate, smaller file set uploaded specifically for Housing Bank",
      "Plain keyword search across every indexed page and slide",
      "Jumps straight to the exact page — no AI involved",
      "Best when you already know the word or phrase you're looking for",
    ],
    { x: 8.1, y: 1.6, w: 4.6, fontSize: 13, gap: 14 },
  );
}

// ================= Slide 9: Ask AI feature =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Ask AI: a conversation over the Index", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("askai-empty.jpg"), x: MARGIN, y: 1.35, w: 7.3 });
  bulletList(
    s,
    [
      "Full chat interface — type or speak your question",
      "Answers are generated only from the Index's own files",
      "If nothing relevant is indexed, it says so — it will not guess",
      "Shows the exact file and page/slide each answer came from",
    ],
    { x: 8.1, y: 1.6, w: 4.6, fontSize: 13, gap: 14 },
  );
}

// ================= Slide 10: Closing =================
{
  const s = pres.addSlide({ masterName: "CLOSING" });
  s.addText("Grounded in your own documents, nothing else", { placeholder: "title" });
  bulletList(
    s,
    [
      "Every answer traces back to a slide your team uploaded",
      "No answer invented from general knowledge",
      "Works in English and Arabic",
      "Admins control exactly what the bot can see",
    ],
    { x: 0.9, y: 4.25, w: 10.5, fontSize: 15, color: THEME.colors.lt1, gap: 14 },
  );
}

(async () => {
  await pres.writeFile({ fileName: path.join(__dirname, "housing-bank-chatbot.pptx") });
  const { applyTheme } = require(path.join(
    "C:", "Users", "Motasem Sanouri", ".claude", "skills", "synced",
    "39d02294-e652-4222-bc3f-3519f1f37a81_02cd50f1-90f3-4388-80db-244cb5ee4495", "pptx", "scripts", "apply_theme.js",
  ));
  await applyTheme(path.join(__dirname, "housing-bank-chatbot.pptx"), THEME);
  console.log("done");
})();
