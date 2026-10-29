const pptxgen = require("pptxgenjs");
const path = require("path");

const THEME = {
  name: "Vita Bot",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "0B1A3A",
    lt1: "FFFFFF",
    dk2: "102A5C",
    lt2: "E7F1FC",
    accent1: "1C8FE3",
    accent2: "4FB3E8",
    accent3: "8FC7F2",
    accent4: "2FA88F",
    accent5: "8C98AC",
    accent6: "1472BE",
    hlink: "1C8FE3",
    folHlink: "1472BE",
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };

const ASSET = (f) => path.join(__dirname, "assets-vita", f);
const PAGE_W = 13.333;
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
          fontFace: THEME.headFontFace, fontSize: 28, bold: true, color: THEME.colors.dk2, align: "left" },
        text: "",
      } },
    { text: { text: "Vita Bot · AI Chatbot", options: {
          x: PAGE_W - 3.6, y: 7.08, w: 3.0, h: 0.3, fontFace: THEME.bodyFontFace, fontSize: 9,
          color: THEME.colors.accent5, align: "right", margin: 0,
        } } },
  ],
  slideNumber: { x: MARGIN, y: 7.08, fontFace: THEME.bodyFontFace, fontSize: 9, color: THEME.colors.accent5 },
});

pres.defineSlideMaster({
  title: "SECTION",
  background: { color: THEME.colors.dk2 },
  objects: [
    { placeholder: {
        options: { name: "title", type: "title", x: 0.9, y: 3.1, w: 11.5, h: 1.2,
          fontFace: THEME.headFontFace, fontSize: 32, bold: true, color: THEME.colors.lt1, align: "left" },
        text: "",
      } },
  ],
});

pres.defineSlideMaster({
  title: "CLOSING",
  background: { color: THEME.colors.dk1 },
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

function browserFrame(slide, { imgPath, x, y, w, shadow = true }) {
  const h = w / (1366 / 633);
  const barH = 0.22;
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h: h + barH, rectRadius: 0.06,
    fill: { color: "F3F4F6" }, line: { color: "D9DCE3", width: 0.75 },
    shadow: shadow ? { type: "outer", color: "091330", opacity: 0.22, blur: 10, offset: 3, angle: 90 } : undefined,
  });
  [0, 1, 2].forEach((i) => {
    slide.addShape(pres.ShapeType.ellipse, {
      x: x + 0.12 + i * 0.16, y: y + barH / 2 - 0.035, w: 0.07, h: 0.07,
      fill: { color: ["E0645A", "E8B04B", "4CAF7D"][i] }, line: { type: "none" },
    });
  });
  slide.addImage({ path: imgPath, x, y: y + barH, w, h });
  return { h: h + barH };
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

function stepCard(slide, { x, y, w, h, n, title, desc }) {
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.08, fill: { color: THEME.colors.lt2 }, line: { type: "none" },
  });
  iconCircle(slide, { x: x + 0.3, y: y + 0.25, d: 0.5, fill: THEME.colors.accent1, glyph: n, fontSize: 18 });
  slide.addText(title, {
    x: x + 0.95, y: y + 0.23, w: w - 1.2, h: 0.35, fontFace: THEME.headFontFace, fontSize: 15, bold: true,
    color: THEME.colors.dk2, margin: 0, isTextBox: true,
  });
  slide.addText(desc, {
    x: x + 0.3, y: y + 0.85, w: w - 0.6, h: h - 1.0, fontFace: THEME.bodyFontFace, fontSize: 11.5,
    color: THEME.colors.dk1, margin: 0, isTextBox: true, valign: "top",
  });
}

// ================= Slide 1: Title =================
{
  const s = pres.addSlide({ masterName: "TITLE_SLIDE" });
  iconCircle(s, { x: 0.9, y: 1.5, d: 0.62, fill: THEME.colors.accent1, glyph: "✨", fontSize: 22 });
  s.addText("VITA BOT", {
    x: 1.68, y: 1.5, w: 6, h: 0.62, valign: "middle",
    fontFace: THEME.bodyFontFace, fontSize: 13, color: THEME.colors.accent2, bold: true, charSpacing: 3,
    margin: 0, isTextBox: true,
  });
  s.addText("The AI Chatbot Behind Day-to-Day Operations", { placeholder: "title" });
  s.addText(
    "A feature walkthrough and a closer look at how it's built — from document ingestion to the answer a user reads on screen.",
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

// ================= Slide 2: Two roles =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Two ways people use Vita Bot", { placeholder: "title" });
  s.addText("Every account has one of two roles, each with a purpose-built interface.", {
    x: MARGIN, y: 1.2, w: 11, h: 0.4, fontFace: THEME.bodyFontFace, fontSize: 13,
    color: THEME.colors.accent5, margin: 0, isTextBox: true,
  });

  const cardY = 1.95, cardW = 5.65, cardH = 4.6, gap = 0.4;
  const cards = [
    {
      x: MARGIN, fill: THEME.colors.dk2, accent: THEME.colors.accent2,
      kicker: "ADMIN", title: "Builds and manages the knowledge base",
      items: [
        "Uploads manuals, spreadsheets, and procedure guides",
        "Organizes a video library linked to real workflows",
        "Writes and curates the FAQ",
        "Adds users and groups them into companies",
        "Reviews every conversation and usage analytics",
        "Resolves the questions the bot couldn't answer",
        "Has a private assistant for questions about their own account data",
      ],
    },
    {
      x: MARGIN + cardW + gap, fill: THEME.colors.lt2, accent: THEME.colors.dk2,
      kicker: "MEMBER", title: "Asks questions, watches, and learns",
      items: [
        "Asks the chatbot questions by text or voice",
        "Browses the FAQ for common answers",
        "Watches the video library, organized by topic",
        "Gets a support ticket opened automatically if the bot can't help",
        "No access to uploads, other users, or account settings",
      ],
      dark: false,
    },
  ];

  cards.forEach((c) => {
    s.addShape(pres.ShapeType.roundRect, {
      x: c.x, y: cardY, w: cardW, h: cardH, rectRadius: 0.08,
      fill: { color: c.fill }, line: { type: "none" },
      shadow: { type: "outer", color: "091330", opacity: 0.18, blur: 12, offset: 3, angle: 90 },
    });
    s.addText(c.kicker, {
      x: c.x + 0.4, y: cardY + 0.3, w: cardW - 0.8, h: 0.3,
      fontFace: THEME.bodyFontFace, fontSize: 11, bold: true, color: c.accent, charSpacing: 2,
      margin: 0, isTextBox: true,
    });
    s.addText(c.title, {
      x: c.x + 0.4, y: cardY + 0.6, w: cardW - 0.8, h: 0.75,
      fontFace: THEME.headFontFace, fontSize: 17, bold: true,
      color: c.dark === false ? THEME.colors.dk1 : THEME.colors.lt1,
      margin: 0, isTextBox: true,
    });
    bulletList(s, c.items, {
      x: c.x + 0.4, y: cardY + 1.45, w: cardW - 0.8, fontSize: 12.5,
      color: c.dark === false ? THEME.colors.dk1 : THEME.colors.lt1, gap: 10,
    });
  });
}

// ================= Slide 3: Section divider - how it's built =================
{
  const s = pres.addSlide({ masterName: "SECTION" });
  s.addText("How it's built", { placeholder: "title" });
  s.addText("From an uploaded manual to a trustworthy answer", {
    x: 0.9, y: 4.35, w: 10, h: 0.5, fontFace: THEME.bodyFontFace, fontSize: 16,
    italic: true, color: THEME.colors.accent3, margin: 0, isTextBox: true,
  });
}

// ================= Slide 4: Ingestion pipeline =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Step 1 — Turning documents into searchable knowledge", { placeholder: "title" });
  s.addText(
    "Every file your team uploads — a PDF manual, a spreadsheet, a slide deck — is broken into small, " +
      "self-contained passages. Each passage is converted into a numeric representation of its meaning " +
      "(an embedding), not just its exact wording, and stored alongside the original text.",
    {
      x: MARGIN, y: 1.2, w: 11.9, h: 0.9, fontFace: THEME.bodyFontFace, fontSize: 13.5,
      color: THEME.colors.dk1, margin: 0, isTextBox: true,
    },
  );

  const types = [
    { icon: "picture_as_pdf", label: "PDF Manuals", desc: "Step-by-step procedure guides, split page by page" },
    { icon: "table_chart", label: "Spreadsheets", desc: "Error lists and reference tables, row by row" },
    { icon: "smart_display", label: "Video Library", desc: "Short how-to clips, organized by topic and linked to FAQ entries" },
    { icon: "quiz", label: "FAQ Entries", desc: "Hand-written Q&A pairs for the most common questions" },
  ];
  const cardW = 2.78, gapX = 0.2, startX = MARGIN, y = 2.35, h = 2.3;
  types.forEach((t, i) => {
    const x = startX + i * (cardW + gapX);
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w: cardW, h, rectRadius: 0.08, fill: { color: THEME.colors.lt2 }, line: { type: "none" },
    });
    iconCircle(s, { x: x + cardW / 2 - 0.3, y: y + 0.3, d: 0.6, fill: THEME.colors.accent1, glyph: "●", fontSize: 10, glyphColor: THEME.colors.accent1 });
    s.addText(t.label, {
      x: x + 0.2, y: y + 1.05, w: cardW - 0.4, h: 0.4, align: "center",
      fontFace: THEME.headFontFace, fontSize: 13.5, bold: true, color: THEME.colors.dk2, margin: 0, isTextBox: true,
    });
    s.addText(t.desc, {
      x: x + 0.2, y: y + 1.45, w: cardW - 0.4, h: 0.8, align: "center",
      fontFace: THEME.bodyFontFace, fontSize: 10.5, color: THEME.colors.dk1, margin: 0, isTextBox: true,
    });
  });

  s.addText(
    "Why embeddings, not keyword search: a user who asks “how do I take money out of the till” still " +
      "matches a passage written as “إدخال / إخراج مبلغ مالي من نقطة البيع” — the search works on meaning, " +
      "across languages, not on matching exact words.",
    {
      x: MARGIN, y: 4.85, w: 11.9, h: 0.9, fontFace: THEME.bodyFontFace, fontSize: 12.5, italic: true,
      color: THEME.colors.accent6, margin: 0, isTextBox: true,
    },
  );
}

// ================= Slide 5: Retrieval + generation =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Step 2 — Answering a real question", { placeholder: "title" });

  const steps = [
    { n: "1", t: "Match", d: "The question is compared against every stored passage, and only the handful that are genuinely close in meaning are kept." },
    { n: "2", t: "Filter", d: "Passages from an unrelated topic are discarded, even if they share a few words with the question." },
    { n: "3", t: "Write", d: "The AI composes a complete, natural answer using only the surviving passages — in the language the question was asked in." },
    { n: "4", t: "Decline", d: "If nothing genuinely relevant was found, it says so plainly instead of guessing — and offers to open a support ticket." },
  ];
  const stepW = 2.78, stepGap = 0.2, startX = MARGIN, y = 1.3, h = 2.1;
  steps.forEach((st, i) => {
    stepCard(s, { x: startX + i * (stepW + stepGap), y, w: stepW, h, n: st.n, title: st.t, desc: st.d });
  });

  s.addText("Live example", {
    x: MARGIN, y: 3.75, w: 6, h: 0.3, fontFace: THEME.bodyFontFace, fontSize: 12, bold: true,
    color: THEME.colors.accent6, margin: 0, isTextBox: true,
  });
  browserFrame(s, { imgPath: ASSET("chat-en.jpg"), x: MARGIN, y: 4.1, w: 5.5 });
  s.addText(
    "The question matched the “POS sale refund” procedure, so the answer lists every step from that " +
      "procedure in order — nothing skipped, nothing added — and the attached training video is surfaced " +
      "automatically underneath it.",
    {
      x: MARGIN + 5.5 + 0.4, y: 4.25, w: 5.4, h: 2.5, fontFace: THEME.bodyFontFace, fontSize: 13,
      italic: true, color: THEME.colors.dk1, valign: "top", margin: 0, isTextBox: true,
    },
  );
}

// ================= Slide 6: Arabic example (text-quote styling, not a screenshot) =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("The same question, in Arabic", { placeholder: "title" });
  s.addText(
    "Vita Bot answers in whatever language the question was asked in — even when the source manual is " +
      "written only in Arabic or only in English. This is a real exchange from the member chat:",
    {
      x: MARGIN, y: 1.2, w: 11.9, h: 0.6, fontFace: THEME.bodyFontFace, fontSize: 13,
      color: THEME.colors.accent5, margin: 0, isTextBox: true,
    },
  );

  s.addShape(pres.ShapeType.roundRect, {
    x: 2.4, y: 2.1, w: 8.5, h: 4.4, rectRadius: 0.1, fill: { color: THEME.colors.dk2 }, line: { type: "none" },
    shadow: { type: "outer", color: "091330", opacity: 0.2, blur: 12, offset: 3, angle: 90 },
  });
  s.addText("سؤال", {
    x: 2.8, y: 2.45, w: 7.7, h: 0.3, align: "right", fontFace: THEME.bodyFontFace, fontSize: 11, bold: true,
    color: THEME.colors.accent2, charSpacing: 1, margin: 0, isTextBox: true,
  });
  s.addText("كيف أطبع ملصقات الباركود للمنتجات؟", {
    x: 2.8, y: 2.78, w: 7.7, h: 0.5, align: "right", fontFace: THEME.headFontFace, fontSize: 18, bold: true,
    color: THEME.colors.lt1, margin: 0, isTextBox: true, rtlMode: true,
  });
  s.addShape(pres.ShapeType.line, {
    x: 2.8, y: 3.5, w: 7.7, h: 0, line: { color: "2A4E8C", width: 1 },
  });
  s.addText("الجواب", {
    x: 2.8, y: 3.65, w: 7.7, h: 0.3, align: "right", fontFace: THEME.bodyFontFace, fontSize: 11, bold: true,
    color: THEME.colors.accent2, charSpacing: 1, margin: 0, isTextBox: true,
  });
  s.addText(
    "لطباعة ملصقات الباركود للمنتجات، اتبع الخطوات التالية:\n" +
      "1. من قسم المخزون، انتقل إلى إعداد التقارير.\n" +
      "2. اختر Product Barcode Label.\n" +
      "3. قم باختيار المنتجات التي ترغب بطباعة ملصقات لها وعدد مرات الطباعة.\n" +
      "4. اضغط على Print.",
    {
      x: 2.8, y: 3.98, w: 7.7, h: 2.3, align: "right", fontFace: THEME.bodyFontFace, fontSize: 14,
      color: THEME.colors.lt1, margin: 0, isTextBox: true, valign: "top", lineSpacing: 22,
    },
  );
}

// ================= Slide 7: Admin - Knowledge Base upload =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Admin: uploading to the Knowledge Base", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("kb-upload.jpg"), x: MARGIN, y: 1.35, w: 7.3 });
  bulletList(
    s,
    [
      "Files, categories, images, and video links all live in one place",
      "Categories keep topics separate — Inventories, POS, Purchase, problems",
      "Each category has its own lock icon — admins choose what's visible",
      "Supported formats: PDF, Word, Excel, Text, and PowerPoint",
    ],
    { x: 8.1, y: 1.6, w: 4.6, fontSize: 13, gap: 14 },
  );
}

// ================= Slide 8: Admin - Knowledge Base library =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Admin: the library view", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("kb-library.jpg"), x: MARGIN, y: 1.35, w: 7.3 });
  bulletList(
    s,
    [
      "Every file, image, video, link, and FAQ question in one category, at a glance",
      "Status badges show when a file is still processing versus ready to answer from",
      "Edit or remove anything without touching the rest of the category",
    ],
    { x: 8.1, y: 1.6, w: 4.6, fontSize: 13, gap: 16 },
  );
}

// ================= Slide 9: Admin - FAQ =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Admin: curating the FAQ", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("faq-list.jpg"), x: MARGIN, y: 1.35, w: 7.3 });
  bulletList(
    s,
    [
      "Hand-written answers for the questions members ask most",
      "Each entry supports English and Arabic — fill either side and the other auto-translates",
      "Organized into categories, with an Error Solutions tab for known issues",
      "Shown to members directly, and used as extra context for the chatbot",
    ],
    { x: 8.1, y: 1.6, w: 4.6, fontSize: 12.5, gap: 13 },
  );
}

// ================= Slide 10: Admin - Companies + Analytics =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Admin: organization and insight", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("companies.jpg"), x: MARGIN, y: 1.3, w: 5.5 });
  browserFrame(s, { imgPath: ASSET("analytics.jpg"), x: MARGIN + 5.5 + 0.35, y: 1.3, w: 5.5 });
  s.addText("Companies", {
    x: MARGIN, y: 4.05, w: 5.5, h: 0.3, fontFace: THEME.headFontFace, fontSize: 13, bold: true,
    color: THEME.colors.dk2, margin: 0, isTextBox: true,
  });
  s.addText("Groups users under their own company — useful when one account covers several branches or teams.", {
    x: MARGIN, y: 4.35, w: 5.5, h: 0.8, fontFace: THEME.bodyFontFace, fontSize: 12,
    color: THEME.colors.dk1, margin: 0, isTextBox: true,
  });
  s.addText("Analytics", {
    x: MARGIN + 5.5 + 0.35, y: 4.05, w: 5.5, h: 0.3, fontFace: THEME.headFontFace, fontSize: 13, bold: true,
    color: THEME.colors.dk2, margin: 0, isTextBox: true,
  });
  s.addText("Question volume, response time, and satisfaction — tracked over 7, 30, or 90 days.", {
    x: MARGIN + 5.5 + 0.35, y: 4.35, w: 5.5, h: 0.8, fontFace: THEME.bodyFontFace, fontSize: 12,
    color: THEME.colors.dk1, margin: 0, isTextBox: true,
  });
}

// ================= Slide 11: Admin - Support Tickets + Admin Assistant =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("Admin: when the bot needs help", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("support-tickets.jpg"), x: MARGIN, y: 1.3, w: 5.5 });
  browserFrame(s, { imgPath: ASSET("admin-assistant.jpg"), x: MARGIN + 5.5 + 0.35, y: 1.3, w: 5.5 });
  s.addText("Support Tickets", {
    x: MARGIN, y: 4.05, w: 5.5, h: 0.3, fontFace: THEME.headFontFace, fontSize: 13, bold: true,
    color: THEME.colors.dk2, margin: 0, isTextBox: true,
  });
  s.addText("Every question the bot couldn't answer becomes a ticket an admin can resolve by hand — and that answer can then be added back to the knowledge base.", {
    x: MARGIN, y: 4.35, w: 5.5, h: 1.0, fontFace: THEME.bodyFontFace, fontSize: 12,
    color: THEME.colors.dk1, margin: 0, isTextBox: true,
  });
  s.addText("Admin Assistant", {
    x: MARGIN + 5.5 + 0.35, y: 4.05, w: 5.5, h: 0.3, fontFace: THEME.headFontFace, fontSize: 13, bold: true,
    color: THEME.colors.dk2, margin: 0, isTextBox: true,
  });
  s.addText("A second, separate assistant just for admins — ask about your own documents, categories, and drafts instead of digging through menus.", {
    x: MARGIN + 5.5 + 0.35, y: 4.35, w: 5.5, h: 1.0, fontFace: THEME.bodyFontFace, fontSize: 12,
    color: THEME.colors.dk1, margin: 0, isTextBox: true,
  });
}

// ================= Slide 12: Member side =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("The member experience", { placeholder: "title" });
  browserFrame(s, { imgPath: ASSET("member-topbar.jpg"), x: MARGIN, y: 1.35, w: 7.3 });
  bulletList(
    s,
    [
      "A simple top bar instead of the admin sidebar",
      "Bot — the main chat",
      "FAQ — common questions, answered in advance",
      "Videos — a full library of short how-to clips",
      "No visibility into uploads, other users, or account settings",
    ],
    { x: 8.1, y: 1.6, w: 4.6, fontSize: 13, gap: 15 },
  );
}

// ================= Slide 13: Video library =================
{
  const s = pres.addSlide({ masterName: "CONTENT" });
  s.addText("The video library, by the numbers", { placeholder: "title" });
  s.addText(
    "Every video is grouped under the same categories as the written manuals, so a member who doesn't want " +
      "to read can still find the same answer as a short clip.",
    {
      x: MARGIN, y: 1.2, w: 11.9, h: 0.6, fontFace: THEME.bodyFontFace, fontSize: 13,
      color: THEME.colors.accent5, margin: 0, isTextBox: true,
    },
  );

  const cats = [
    { label: "Inventories", count: "11", sample: "عرض تقارير حركات المنتجات · كيفية عمل إتلاف منتجات · طباعة الملصقات" },
    { label: "POS", count: "16", sample: "فتح جلسة وآلية البيع · مرتجع المبيعات · نقاط الولاء · إغلاق جلسة البيع" },
    { label: "Purchase", count: "8", sample: "إنشاء فاتورة مورد · إعادة الطلب التلقائي · مرتجع مورد / إشعار دائن" },
  ];
  const cardW = 3.75, gapX = 0.28, startX = MARGIN, y = 2.1, h = 3.8;
  cats.forEach((c, i) => {
    const x = startX + i * (cardW + gapX);
    s.addShape(pres.ShapeType.roundRect, {
      x, y, w: cardW, h, rectRadius: 0.08, fill: { color: THEME.colors.lt2 }, line: { type: "none" },
    });
    s.addText(c.count, {
      x: x + 0.3, y: y + 0.3, w: cardW - 0.6, h: 0.9, fontFace: THEME.headFontFace, fontSize: 44, bold: true,
      color: THEME.colors.accent1, margin: 0, isTextBox: true,
    });
    s.addText(c.label + " videos", {
      x: x + 0.3, y: y + 1.15, w: cardW - 0.6, h: 0.35, fontFace: THEME.bodyFontFace, fontSize: 13, bold: true,
      color: THEME.colors.dk2, margin: 0, isTextBox: true,
    });
    s.addShape(pres.ShapeType.line, { x: x + 0.3, y: y + 1.65, w: cardW - 0.6, h: 0, line: { color: THEME.colors.accent3, width: 1 } });
    s.addText(c.sample, {
      x: x + 0.3, y: y + 1.85, w: cardW - 0.6, h: h - 2.1, align: "right", fontFace: THEME.bodyFontFace,
      fontSize: 12, color: THEME.colors.dk1, margin: 0, isTextBox: true, valign: "top", lineSpacing: 20,
    });
  });
}

// ================= Slide 14: Closing =================
{
  const s = pres.addSlide({ masterName: "CLOSING" });
  s.addText("Built on your team's own knowledge", { placeholder: "title" });
  bulletList(
    s,
    [
      "Manuals, spreadsheets, FAQ entries, and videos — all one searchable source",
      "Every answer traces back to something your team actually wrote or recorded",
      "No answer invented from general knowledge",
      "Works in English and Arabic, in the same conversation",
      "Unanswered questions become tickets, and tickets become new knowledge",
    ],
    { x: 0.9, y: 4.0, w: 10.5, fontSize: 15, color: THEME.colors.lt1, gap: 13 },
  );
}

(async () => {
  await pres.writeFile({ fileName: path.join(__dirname, "vita-bot-deepdive.pptx") });
  const { applyTheme } = require(path.join(
    "C:", "Users", "Motasem Sanouri", ".claude", "skills", "synced",
    "39d02294-e652-4222-bc3f-3519f1f37a81_02cd50f1-90f3-4388-80db-244cb5ee4495", "pptx", "scripts", "apply_theme.js",
  ));
  await applyTheme(path.join(__dirname, "vita-bot-deepdive.pptx"), THEME);
  console.log("done");
})();
