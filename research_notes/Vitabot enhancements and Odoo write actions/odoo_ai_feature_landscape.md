# Feature Landscape: Odoo-native AI, Third-Party Odoo AI Apps, and Enterprise Copilots (as of Nov 2026)

Context: written for "vitabot", a multi-tenant AI chatbot for Odoo that users reach through Odoo SSO. Today it answers questions from a knowledge base and has admin analytics (top questions, weak or no-info answers, ratings, digests), support tickets, videos and media, and Arabic/English support. Odoo versions referenced: Odoo 18 (2024), Odoo 19 (released at Odoo Experience, Sept 2025), and Odoo 20 (launched 24 Sept 2026, per third-party coverage).

## 1. What does Odoo's native AI offer (Odoo 19 and Odoo 20)?

### Takeaway
Odoo 19 (Sept 2025) introduced an AI app built around configurable agents: a system prompt, "topics" (bundles of instructions and tools), RAG "sources" and an optional "Restrict to Sources" mode. Agents were exposed through an Ask AI button and Ctrl+K, live chat, AI fields, AI server actions and email templates. In 19 they were mostly read/navigate-only, except for lead creation. Odoo 20 (Sept 2026) made agents transactional: they create and update records with preview and confirmation, run from automated and scheduled actions, and connect outward through MCP. "Topics" were renamed "skills". All AI moved onto paid IAP credits (€1/credit) and remains Enterprise-only. The native product now overlaps heavily with a knowledge-base chatbot, so vitabot's differentiation has to come from elsewhere: analytics/feedback loops, tenant-managed KB curation, Arabic quality, channels, cost predictability, and Community or Standard-plan reach.

### Cited Findings

**Odoo 19 agent architecture (official docs)**
- An agent consists of a System Prompt, Topics and Sources. With no topics, an agent "can only provide information" and cannot complete tasks or change the database. — [Odoo 19 docs: AI agents](https://www.odoo.com/documentation/19.0/applications/productivity/ai/agents.html)
- The built-in topics in 19 are *Natural Language Search* (interprets the query and opens the matching Odoo view with search filters), *Information retrieval* (tools for reading model data) and *Create Leads* (available only if CRM is installed). Which tools are available depends on the installed apps. — [Odoo 19 docs: AI agents](https://www.odoo.com/documentation/19.0/applications/productivity/ai/agents.html)
- Sources can be PDFs, web links (one per line), files from the Documents app and Knowledge articles. Sources are indexed, with status going from Processing to Indexed, and each one must be toggled Active. Upload failures can come from a conflict with the selected LLM. — [Odoo 19 docs: AI agents](https://www.odoo.com/documentation/19.0/applications/productivity/ai/agents.html)
- "Restrict to Sources" limits answers to the uploaded, active sources. The agent has three response styles: Analytical (more consistent), Balanced and Creative. A Test button opens a trial conversation. — [Odoo 19 docs: AI agents](https://www.odoo.com/documentation/19.0/applications/productivity/ai/agents.html)
- The LLM is picked per agent from a drop-down. Odoo supports "multiple versions of ChatGPT and Gemini." — [Odoo 19 docs: AI agents](https://www.odoo.com/documentation/19.0/applications/productivity/ai/agents.html); the 19 release notes list "ChatGPT 5.0" support and "Connect your own Gemini account". — [Odoo 19 release notes](https://www.odoo.com/odoo-19-release-notes)
- Ask AI can be opened from the command palette (Ctrl+K) or from an AI button in the top-right, which shows location-specific suggested prompts. A response can be sent as an email, logged as a chatter note or copied, and a conversation can be moved into Discuss. The standard Ask AI agent "cannot" change records. — [Odoo 19 docs: AI overview](https://www.odoo.com/documentation/19.0/applications/productivity/ai.html)
- AI subpages in 19 cover API keys, agents, default prompts, document sort, AI fields, live chat, server actions, email templates, voice transcription, improve-text and support workflows. — [Odoo 19 docs: AI overview](https://www.odoo.com/documentation/19.0/applications/productivity/ai.html)

**Odoo 19 release-note AI items**
- Agents learn from documents and can perform actions. Internal users can ask an agent about their own database records. "Ask AI search" turns natural language into an Odoo search domain. AI fields fill in field values. Draft with Odoo AI writes emails, improves text and summarizes chatter. Email templates can embed AI prompts for single or mass sends. AI fields and server actions can read attached files and search the web. A livechat AI agent can create leads. Default prompts and agent assignment depend on where AI is invoked ("unified AI workflows"). Voice transcription works in real time and produces a summary. Website pages can be generated from a prompt. Documents can be sorted and actions triggered by AI prompts. HTML property fields can be AI-filled. CRM has AI win-probability insights. — [Odoo 19 release notes](https://www.odoo.com/odoo-19-release-notes)

**Odoo 19 live chat AI**
- Installing Live Chat and AI adds a preconfigured "Livechat AI Agent", which is attached to a channel through a Rules-tab rule. When a channel has both a scripted chatbot and an AI agent, the AI agent takes priority. — [Odoo 19 docs: AI live chat](https://www.odoo.com/documentation/19.0/applications/productivity/ai/live-chat.html)
- When information is incomplete, the agent avoids guessing and moves toward human follow-up. It escalates on custom pricing or contracts, account changes or troubleshooting, demo or contact requests, and low confidence. The *Lead Creation* topic collects missing contact details one at a time, confirms what is known and calls the lead-creation tool exactly once, preventing duplicate leads. — [Odoo 19 docs: AI live chat](https://www.odoo.com/documentation/19.0/applications/productivity/ai/live-chat.html)
- The docs page does not cover language support for the live chat agent. — [Odoo 19 docs: AI live chat](https://www.odoo.com/documentation/19.0/applications/productivity/ai/live-chat.html)

**Odoo 19 Helpdesk/support AI**
- AI fields condense long tickets into key points and update when the record changes. AI automations categorize and prioritize tickets "automatically as soon as a ticket is created". Agents draft replies from the system prompt, ticket context and sources, while "agents remain in control" of what is sent to the customer. A default prompt places an AI button on the ticket form. — [Odoo 19 docs: AI in support workflows](https://www.odoo.com/documentation/19.0/applications/productivity/ai/support_operations.html)

**Odoo 19 keys and editions**
- On Odoo.sh and on-premise, the customer must supply API keys (OpenAI or Gemini). On Odoo Online, bringing your own key is optional. Provider fees apply. — [Odoo 19 docs: AI API keys](https://www.odoo.com/documentation/19.0/applications/productivity/ai/apikeys.html)
- The AI app, agents, AI fields and voice are Enterprise-only, and Community has no native AI. — [oec.sh guide](https://oec.sh/guides/odoo-ai-community); [ERPClaw (vendor of an open-source competitor, so biased)](https://www.erpclaw.ai/blog/odoo-enterprise-ai-pricing-2026/)
- The release timing is disputed. Some sources say the AI app first appeared in Odoo Online 18.3, others that it arrived with Odoo 19 in Sept 2025. — summarized from search results incl. [muchconsulting](https://muchconsulting.com/blog/odoo-2/odoo-ai-technical-138) and [Brainvire](https://www.brainvire.com/odoo-erp/odoo-19/) (not independently verified)
- Odoo Experience 2025 sessions included "Odoo AI: Setup your own agents (RAG)" and "Build custom agents to streamline your operations". The latter describes agents that answer from uploaded documents and web content and take actions such as creating calendar events. — [OXP 2025 track: RAG agents](https://www.odoo.com/event/odoo-experience-2025-6601/track/odoo-ai-setup-your-own-agents-rag-8342); [OXP 2025 track: custom agents](https://www.odoo.com/event/odoo-experience-2025-6601/track/odoo-ai-build-custom-agents-to-streamline-your-operations-8764)

**Odoo 20 (Sept 2026), from the official release notes**
- All AI features now require credits bought through IAP. "Connect Odoo to anything" adds a Model Context Protocol (MCP) server. — [Odoo 20 release notes](https://www.odoo.com/odoo-20-release-notes)
- Agentic automation: agents can update their own configuration, be triggered by automated or scheduled actions, show how they handled past chats, and get a role-based avatar. "Model-bound" agents offer to become a model's default agent. Conversations are stored for up to 30 days after the last message. When the tool-call limit is reached, the agent asks the user to confirm before continuing. Users answer questions, permission requests and suggestions with buttons. "Live updates" show specific progress instead of a generic "thinking" indicator. Default prompts can carry context and dynamic values. Topics are renamed Skills. — [Odoo 20 release notes](https://www.odoo.com/odoo-20-release-notes)
- Agent capabilities: create records (including from an uploaded PDF of instructions), update records, ask questions about a file while previewing it, send or link files in chat, filter by time period (week or quarter) when building views, generate images and enriched buttons for websites and mailings, and manually reprocess sources so the latest version is used. — [Odoo 20 release notes](https://www.odoo.com/odoo-20-release-notes)
- Interaction: a "+" menu adds options to a request, users can dictate requests by voice, and live chat shows clickable record preview cards when the agent mentions a record. — [Odoo 20 release notes](https://www.odoo.com/odoo-20-release-notes)
- App-specific: Accounting has "AI-powered financial insights", which answer finance questions "based only on the accounting data in your database". In eCommerce, an AI assistant generates product images and edits name, price and description. Documents can rename files with AI. — [Odoo 20 release notes](https://www.odoo.com/odoo-20-release-notes)
- The Odoo 20 docs say AI requests go through Odoo's IAP service and "AI usage consumes IAP credits". An external agent can connect through the Odoo MCP server. Installing the AI app on the Standard plan "automatically triggers an upsell" to the Custom plan. — [Odoo 20 docs: AI](https://www.odoo.com/documentation/20.0/applications/productivity/ai.html)
- Third-party analysis says "AI agents: create/update records" shipped. AI in the website builder and shop shipped. WhatsApp/SMS in automation shipped only partly. An accounting agent shown in the launch video is not clearly in the release notes, and about 20 announced "industry" AI versions shipped only partly. — [Macopedia](https://macopedia.com/en/blog/news/odoo-20-whats-new)
- Limits and controls reported for 20: the agent stops and asks after 30 consecutive tool rounds by default. "Self Update" is on by default, with confirmation. Create/Update shows a preview for confirmation, and an "Auto-Approve Actions" option skips it. AI server-action tools run unconditionally, so business rules must live in the tool code. MCP exposes five read tools by default and uses the connecting user's permissions. Credits belong to one database and cannot be transferred. — [iVenture Team (third-party, citing Odoo docs/IAP)](https://iventureteam.com/blog/odoo-20-ai-features-and-iap-credits-monthly-cost-breakdown/)

**Pricing (Odoo 20)**
- Odoo AI costs €1 per credit, in packs of 10 to 1,000, with 20 free credits. Consumption "varies based on the specific AI feature, task complexity, and the size of your request", and no per-run rate is published. Document Digitization costs €0.15 down to €0.05 per document, with 200 free. — [iVenture Team, citing Odoo IAP](https://iventureteam.com/blog/odoo-20-ai-features-and-iap-credits-monthly-cost-breakdown/)
- Plan prices: US$31.10/user/month for Standard and US$61.00 for Custom (yearly billing). Because the AI app on Standard forces an upsell to Custom, adding AI roughly doubles the per-user cost. — [iVenture Team](https://iventureteam.com/blog/odoo-20-ai-features-and-iap-credits-monthly-cost-breakdown/); the Standard figure matches [ERPClaw](https://www.erpclaw.ai/blog/odoo-enterprise-ai-pricing-2026/) ($31.10 in body; its headline says $24.90, an internal inconsistency)
- Databases that used their own OpenAI or Gemini key in 19 need IAP credits after upgrading to 20, and custom code that called the old services must be rewritten. — [iVenture Team](https://iventureteam.com/blog/odoo-20-ai-features-and-iap-credits-monthly-cost-breakdown/)

### Inferences
- In Odoo 20, native agents cover the core of vitabot's current offer: KB/RAG answers from PDFs, links and Knowledge articles, plus live chat with escalation to leads. Vitabot's defensible areas are likely to be: (a) Community and Standard-plan customers, who cannot use native AI without the Custom upsell; (b) tenants who want predictable flat pricing rather than per-credit spend; (c) the analytics and feedback loop (top questions, no-info detection, ratings, digests), which Odoo does not document beyond "show how they handled past chats"; (d) Arabic quality and MENA channels; (e) cross-tenant content management, such as a vendor or partner publishing one KB to many client databases.
- Odoo's UX patterns are now the baseline Odoo users will expect: button-based confirmations, previews before writes, live progress, record preview cards, voice dictation, file Q&A and a tool-call limit with a confirmation prompt. Vitabot should match them if it adds write actions.
- Native 30-day chat retention suggests a gap vitabot can fill: long-term analytics history and audit.

### Gaps
- No official, Odoo-published per-action credit consumption rates exist.
- The official docs pages fetched do not describe how native agents enforce the user's ACLs or record rules on RAG sources. Forum evidence shows record rules do apply to agents ([Odoo forum](https://www.odoo.com/fi_FI/forum/apua-1/providing-access-of-ai-agent-to-particular-group-281570)), but no detailed doc was found.
- No official statement was found on Arabic quality or RTL behaviour of the native AI.
- The Odoo 20 release notes were truncated after the eCommerce section, so AI items in Helpdesk, WhatsApp and other later sections may be missing.

## 2. What do popular third-party Odoo AI apps offer?

### Takeaway
The apps.odoo.com AI catalogue in 2026 is dominated by free MCP servers. These let Claude, ChatGPT or Gemini read and write Odoo using the user's own permissions, and they compete on governance: scoped API keys, OAuth 2.1, per-model whitelists, immutable audit logs, dry runs, approvals and undoable writes. A second group offers in-Odoo assistants: natural-language-to-data, voice queries, accounting Q&A with charts, document extraction, and WhatsApp AI auto-reply. Search sorted by downloads shows mostly free apps. Paid examples are WhatsApp AI bots at roughly $25 to $249. Star ratings are not shown in search listings.

### Cited Findings

**Scale of the catalogue**
- A search for "AI assistant" returns 335 apps, and a search for "chatgpt" returns 408. The top 20 by downloads are all free. — [apps.odoo.com search "AI assistant"](https://apps.odoo.com/apps/modules/browse?search=AI%20assistant&order=Downloads); [apps.odoo.com search "chatgpt"](https://apps.odoo.com/apps/modules/browse?search=chatgpt&order=Downloads)

**MCP servers (governance features)**
- *MCP Server* (much. Consulting, v20, free) is the top result by downloads. It connects AI assistants to Odoo through MCP. — [apps.odoo.com search](https://apps.odoo.com/apps/modules/browse?search=AI%20assistant&order=Downloads)
- *MCP Server (Native)* (ERP Heritage, v20) offers scoped API keys, per-model permissions and audit logs. *Odoo MCP Server Advance* (PyBeans, v19) offers bearer keys, OAuth 2.1, a tool registry, a playground and rate limiting. *Advanced MCP Server* (Linescripts, v19) offers governed writes, approvals, dry runs and audit trails. *Odoo MCP Server* (Faceela FZE LLC, v19, a UAE-registered vendor) offers OAuth 2.1, per-model permissions and an immutable audit log. *MCP Connector Read-only* (Bentley Studios) offers model whitelisting and record limits. — [apps.odoo.com search "AI assistant"](https://apps.odoo.com/apps/modules/browse?search=AI%20assistant&order=Downloads)
- *Odoo MCP Server* (Moaz Nabil, v19, free) offers API keys, OAuth 2.1, a tool registry, **undoable AI writes** and audit logging. *MCP Pro: Audit Log & Scoped API Keys* (Pantalytics) is a companion module for audit and scoped keys. *Cledoo* lets Claude, ChatGPT and Copilot work "under existing permissions". *Speak To Your Database* offers read-only natural-language answers on sales, invoices, stock, CRM and projects. — [apps.odoo.com search "chatgpt"](https://apps.odoo.com/apps/modules/browse?search=chatgpt&order=Downloads)
- *MCP Server | Connect Claude | Connect ChatGPT* (INKERP, v20) is described as an "MCP studio" for natural-language record management, live dashboards and approvals. — [apps.odoo.com search](https://apps.odoo.com/apps/modules/browse?search=AI%20assistant&order=Downloads)
- A forum thread recommends an ai_mcp_server module for using Odoo from Claude, ChatGPT or any MCP chat. — [Odoo forum: ChatGPT integration with Odoo 17](https://www.odoo.com/forum/help-1/chatgpt-integration-with-odoo-17-254302)

**In-Odoo assistants and agents**
- *MuK AI Assistant* (MuK IT, free, v19/20) is the most-downloaded in-Odoo assistant (unlabeled stats 1039/338). It is a "complete agentic AI assistant inside Odoo" that uses the same muk_mcp tool registry as external clients, so in-app and external use share one permission model and audit trail. It has pluggable providers (ChatGPT, Claude, Gemini, plus a separate Mistral module) and a full OWL chat UI at /odoo/ai. — [apps.odoo.com: muk_ai](https://apps.odoo.com/apps/modules/19.0/muk_ai); [search listing](https://apps.odoo.com/apps/modules/browse?search=chatgpt&order=Downloads)
- MuK add-ons: *MuK AI Automation* adds an `ai_agent` server-action state, so any automation can fire an agent, with caps checked before each step. *MuK AI Skills* provides pre-built skills that can be invoked with **slash commands**. *MuK AI MCP* registers remote MCP servers as tools. *MuK AI Enterprise Bridge* reuses Enterprise ai.topic tools and ai.agent.source RAG sources. — [muk_ai_automation](https://apps.odoo.com/apps/modules/19.0/muk_ai_automation); [muk_ai_skills](https://apps.odoo.com/apps/modules/19.0/muk_ai_skills/); [muk_ai_mcp](https://apps.odoo.com/apps/modules/19.0/muk_ai_mcp); [muk_ai_enterprise](https://apps.odoo.com/apps/modules/19.0/muk_ai_enterprise)
- *AI Assistant for Odoo | Free AI Agent & Chatbot | Ask Your Data in Natural Language | Voice Queries* (Aski, v20) offers chat or voice questions on sales and receivables. *AI Assistant* (NullNaveen, v19) reads and totals Odoo data with your own LLM and includes a confirmation step. *Tuqui Assistant* (v20) is a side panel that answers about the open record and "proposes changes you must save". *Aidoo* (PLANOR, v19) covers workflows and contextual actions. *OW AI Assistant* (Openworx) works with any OpenAI-compatible provider. — [apps.odoo.com search "AI assistant"](https://apps.odoo.com/apps/modules/browse?search=AI%20assistant&order=Downloads)
- *AI Accounting & AI Analytics for Community* (Cybrosys, v20, free) offers plain-language accounting queries with tables and charts for P&L, balances, cash and taxes. *AI Documents* (ODI Labs) extracts structured data from uploaded or emailed PDFs and images using Claude, OpenAI, Gemini or a local model, with a review step. *AI Connector for Odoo* (Kalvyai) offers multiple providers (OpenAI, Claude, Gemini, Grok, Azure), **token usage logs and monthly cost limits**. *Odoo AI Automated Actions* (much. GmbH) powers automated actions with ChatGPT, Claude, Gemini or Mistral. *AI Chatbot | Lead Generation Chatbot* (Terabits) is a website chatbot trained on your content that captures leads. *AI Service Center* (odooai.cn) aggregates ChatGPT, DeepSeek, Qwen and Baidu. — [apps.odoo.com search "chatgpt"](https://apps.odoo.com/apps/modules/browse?search=chatgpt&order=Downloads)
- *Odoo AI Chatbot* (TechUltra, v18/19) turns natural-language questions into SQL against the Odoo schema and runs them live, for example "invoices above X in month Y", using an OpenAI key. A forum reply on the listing claims "all languages" are supported, which is unverified. — [apps.odoo.com: odoo_ai_chatbot](https://apps.odoo.com/apps/modules/18.0/odoo_ai_chatbot)
- *AI Assistant for Discuss* (v18) queries records from chat with `$model/id` syntax and works with ChatGPT, Claude or Gemini. — [apps.odoo.com: ai_mail_gt](https://apps.odoo.com/apps/modules/18.0/ai_mail_gt)
- *Claudoo* (cicdoo, embedded, pricing not public) confirms sales orders, posts invoices, validates pickings, runs wizards and scheduled actions, and builds live dashboards. It always runs as the logged-in user, never as superuser. Admins control per-user read, write and act permissions. A one-click "Zero-Trust" switch makes the company read-only, models can be hidden from the AI, and every action is audited, including who it was performed as. It markets "never hallucinated numbers". — [cicdoo.com/claudoo](https://cicdoo.com/claudoo)
- Per-execution credit pricing for some third-party agents is reported at 1 credit per execution for one inventory agent and 7 for another. — [apps.odoo.com: inventory_ai_agent](https://apps.odoo.com/apps/modules/19.0/inventory_ai_agent) (via search snippet; not fetched directly)

**WhatsApp AI apps (Odoo 19)**
- *suite_whatsapp_ai* is a transport layer that bridges Odoo 19's native ai.agent to the WhatsApp Business inbox. Its listing notes that the native agent framework "only works inside the web interface, with no bridge to WhatsApp". — [apps.odoo.com: suite_whatsapp_ai](https://apps.odoo.com/apps/modules/19.0/suite_whatsapp_ai)
- *WhatsApp AI Assistant* (jjro, v16 to 19, Community and Enterprise) auto-replies to routine questions and hands complaints, refunds and negative-sentiment chats to a human. — [apps.odoo.com: jjro_whatsapp_ai](https://apps.odoo.com/apps/modules/19.0/jjro_whatsapp_ai)
- *WhatsApp AI Suite* (Pokutsoft, Community, Meta Cloud API, bring your own key for Claude/OpenAI) — [apps.odoo.com: whatsapp_ai](https://apps.odoo.com/apps/modules/19.0/whatsapp_ai); *TW WhatsApp AI Agent* (Gemini, multi-turn, LGPL-3) — [tw_whatsapp_agent](https://apps.odoo.com/apps/modules/19.0/tw_whatsapp_agent)
- Paid examples: *dev_whatsapp_ai_chatbot_ent* (DevIntelle, $99.08, Enterprise), *ai_whatsapp* ($25.26, Enterprise) and *pragtech_whatsapp_central* ($249, rules, AI or workflow-based auto-replies). — [dev_whatsapp_ai_chatbot_ent](https://apps.odoo.com/apps/modules/19.0/dev_whatsapp_ai_chatbot_ent); [ai_whatsapp](https://apps.odoo.com/apps/modules/19.0/ai_whatsapp); [pragtech_whatsapp_central](https://apps.odoo.com/apps/modules/19.0/pragtech_whatsapp_central) (prices from search snippets)

### Inferences
- MCP has commoditised "talk to Odoo from Claude or ChatGPT", which is free and governance-heavy. Vitabot's added value has to be the managed layer around it: multi-tenant KB, analytics, ticket escalation, media answers, Arabic UX and WhatsApp. Vitabot could also expose itself as an MCP server, or consume Odoo's native MCP in v20 instead of building custom Odoo tools.
- Recurring third-party governance features worth copying for vitabot write actions: run as the logged-in user, per-model allow-lists, read-only kill switch, preview, dry run and approval, undo for AI writes, immutable audit log, token and cost dashboards with monthly caps, and rate limiting.
- Slash-command skills (MuK) and record-context side panels (Tuqui) are UX patterns that fit an SSO-embedded bot.

### Gaps
- apps.odoo.com search listings do not show star ratings or review counts, and individual app pages were not fetched for ratings. Download counts are shown only as unlabeled number pairs.
- Most top apps are free, and paid, higher-revenue AI apps were not systematically sampled (no price-sorted crawl).
- No independent reviews of any of these apps were found.

## 3. Table-stakes feature categories in enterprise copilots (2025–2026)

### Takeaway
Across Microsoft Copilot for Business Central, SAP Joule, Salesforce Agentforce, Oracle NetSuite (Ask Oracle) and Zoho Zia, the common baseline is:
- inherit the user's permissions;
- answer from business data plus documents, sometimes the web;
- navigate to records;
- summarize records;
- analyze lists and data into charts and narratives;
- pre-built role agents (sales order, payables) that keep a human in the loop;
- no-code agent builders with large action libraries;
- MCP or agent-to-agent interoperability;
- trust layers (masking, audit trail, toxicity screening);
- consumption-based pricing (credits, per-conversation or per-action).

Explainability ("see how it reached its answer"), approvals and file upload into chat are now standard too.

### Cited Findings

**Microsoft Copilot in Dynamics 365 Business Central**
- Copilot "inherits their data permissions and can't read any more data than the user already has access to". Prompts are not used for training, and EU Data Boundary is respected. — [Microsoft Learn: Copilot FAQ (updated 2026-11-04)](https://learn.microsoft.com/en-us/dynamics365/business-central/copilot-overview)
- The capability list includes analysis assist on lists (including custom tables), autofill, chat with Copilot (finding records, including in custom tables), marketing text, item substitutions, mapping e-documents to PO lines, **Payables Agent**, bank reconciliation, **Sales Order Agent**, suggested sales lines, suggested number series and **Summarize with Copilot**. — [Microsoft Learn: Copilot FAQ](https://learn.microsoft.com/en-us/dynamics365/business-central/copilot-overview)
- Since update 26.3, some features can search the web for grounding, which admins can configure. Copilot features are included in the BC license at no extra cost, though "fair-use policies, quotas, or pricing might be introduced later". It is available online only, and language and region availability varies per feature (mostly English first). — [Microsoft Learn: Copilot FAQ](https://learn.microsoft.com/en-us/dynamics365/business-central/copilot-overview)
- AI-generated text is treated as a "suggestion only", and human review is required. — [Microsoft Learn: marketing text overview](https://learn.microsoft.com/en-us/dynamics365/business-central/ai-overview)
- Roadmap item RM578065 (GA, Oct 2026) allows multiple Sales Order Agents per company, with better item matching and relevance filtering. — [M365 roadmap mirror](https://mc.merill.net/message/RM578065)
- Agent actions are reviewable in the Copilot pane and carry the agent's own user ID. Agents consume Copilot Credits, which require a consumption billing setup, and run with a human in the loop. — [MS release plan (mirror)](https://dotnet.territoriali.olinfo.it/en-us/dynamics365/release-plan/2025wave2/smb/dynamics365-business-central/use-copilot-agent-capabilities-automate-sales-order-taking-process); [Creative Computing](https://creative-computing.co.uk/resources/dynamics-365-business-centrals-ai-agents-transform-order-to-cash-payables) (partner blog)

**SAP Joule**
- Joule has three interaction patterns: informational, navigational (takes the user to the app answering the question, then hands over) and transactional (task execution). — [SAP Learning: Exploring Joule & Joule Agents](https://learning.sap.com/courses/becoming-an-sap-btp-solution-architect/using-joule)
- Joule Agents are grounded in the SAP Knowledge Graph and Business Data Cloud. Q1 2026 releases mention 30+ specialized agents, 2,500+ Joule Skills, a governed agent gateway for third-party agents and uploading up to 10 PDF or text files into chat. — [SAP Business AI release highlights Q1 2026](https://news.sap.com/2026/04/sap-business-ai-release-highlights-q1-2026/)
- Google Drive grounding and cross-thread search arrived in Q1 2026. — [SAPinsider](https://sapinsider.org/blogs/sap-joule-q1-2026-four-new-features-sap-teams-can-use-today/)

**Salesforce Agentforce**
- Agents are built from topics (job scope), actions (tools) and instructions. Guardrails combine user-defined and managed protections. — [Trailhead: Agentforce guardrails & trust patterns](https://trailhead.salesforce.com/content/learn/modules/trusted-agentic-ai/explore-agentforce-guardrails-and-trust-patterns)
- The Einstein Trust Layer masks sensitive data before it reaches the model, screens output for toxicity and bias, and logs generations. Trailhead recommends its Audit Trail and continuous monitoring. — [Team Ascend](https://blog.teamascend.com/agentforce-einstein-trust-layer); [Trailhead](https://trailhead.salesforce.com/content/learn/modules/trusted-agentic-ai/explore-agentforce-guardrails-and-trust-patterns)
- Reported pricing is about $2 per conversation, about $0.10 per standard action and Flex Credits, plus a pay-per-resolution model for the Help Agent. These come from third-party sources and are not verified against the official price list. — [BD Emerson](https://www.bdemerson.com/article/what-is-agentforce); [Agile Brand Guide](https://agilebrandguide.com/salesforce-debuts-agentforce-help-agent-with-pay-per-resolution-pricing/)
- Hallucination framing: Salesforce material attributes confidently wrong agents largely to bad or unreliable data. — [Trailhead: why an agent can be confidently wrong](https://trailhead.salesforce.com/content/learn/modules/data-reliability-risk-factors-for-ai/understand-why-an-agent-can-be-confidently-wrong); [SalesforceBen](https://www.salesforceben.com/are-agentforce-hallucinations-a-problem-or-is-it-just-your-bad-data/)

**Oracle NetSuite (Ask Oracle, NetSuite 2026.2)**
- Ask Oracle handles plain-language questions from how-to help to data analysis, produces narratives and charts, finds relevant records, pages, reports and dashboards, and is the launch point for agentic workflows while the user keeps approval authority. It follows existing roles and permissions, and users can see how the assistant reached its answers. — [NetSuite: 2026.2 brings Ask Oracle](https://www.netsuite.com/portal/resource/articles/erp/netsuite-2026-2-brings-ask-oracle-capabilities-to-netsuite.shtml); [ERP Today](https://erp.today/netsuite-next-ask-oracle-ai-erp-rollout/)
- "SuiteSkills" adds 45+ AI functions. Ask Oracle Connectors work across NetSuite, other apps and the internet. Rollout started in the US and Canada, with other regions following in 2026–27. — [IT Brief AU](https://itbrief.com.au/story/oracle-netsuite-unveils-new-ai-tools-for-cloud-erp); [Epiq guide](https://epiqinfo.com/netsuite-next-how-ai-is-reshaping-the-erp-you-thought-you-knew/)

**Zoho Zia**
- Zoho has an in-house Zia LLM in three sizes and in-house speech-to-text for English and Hindi only. Zia Agent Studio is prompt-based and no-code with 700+ built-in actions. The Agent Marketplace has about 25 prebuilt agents at launch. An MCP server exposes Zoho actions, and A2A interoperability is planned. — [Futurum Group](https://futurumgroup.com/insights/zoho-unveils-zia-llm-no%E2%80%91code-agent-studio-and-open-agent-interoperability/)
- The suite was announced for MENA (UAE, KSA, Egypt), but no source confirms Arabic support in Zia LLM. — [Arabian Reseller](https://arabianreseller.com/inw6); [Times of Oman](https://timesofoman.com/article/161561-zoho%20launches-zia-llm-and-expands-ai-suite-with-agents-and-studio-tools)
- A June 2026 guide says Agent Studio is free to build and deploy with, model usage is billed separately, and the Store has 100+ agents. This conflicts with the launch figure of about 25. — [Digiwah](https://digiwah.com/zoho-zia-ai/) (weaker source)

**Feature-category matrix (synthesised from the above)**
- Permission inheritance: BC, NetSuite, Odoo MCP, Claudoo, Cledoo — sources above.
- Grounded RAG on docs, plus "restrict to sources": Odoo 19, SAP (Knowledge Graph and file upload), BC (web grounding). — sources above.
- Navigation to records and views: Odoo NL Search, SAP navigational pattern, NetSuite. — sources above.
- Record summarization: BC "Summarize with Copilot", Odoo chatter summaries and AI fields. — sources above.
- Data analysis to charts and narrative: NetSuite, BC analysis assist, Cybrosys accounting AI, Odoo 20 financial insights. — sources above.
- Transactional agents with human-in-the-loop approval: BC Sales Order and Payables Agents, Odoo 20 create/update with preview, NetSuite approval authority. — sources above.
- Triggered or scheduled agents (proactive): Odoo 20, MuK AI Automation. — sources above.
- Agent builder (no-code), skills and action libraries: Zia Agent Studio (700+ actions), Joule Skills (2,500+), Agentforce topics and actions, Odoo skills. — sources above.
- Interoperability through MCP or A2A: Odoo 20, Zoho, SAP agent gateway. — sources above.
- Trust and governance (masking, audit, toxicity, agent identity): Agentforce Trust Layer, BC agent user ID. — sources above.
- Consumption pricing: Odoo IAP credits, Copilot Credits, Agentforce per conversation or action. — sources above.

### Inferences
- For vitabot, the most-cited table-stakes items it likely lacks are: (1) permission-aware live ERP data answers rather than KB only; (2) record summarization in context; (3) navigation deep-links into Odoo views and records; (4) actions with preview and approval and the agent's own audit identity; (5) proactive and scheduled insights (vitabot's "digests" are a seed for this); (6) explainability ("how I got this answer" with citations); (7) file upload into chat; (8) per-feature admin toggles and data-residency statements.
- Vitabot's existing analytics (no-info answers, ratings, top questions) map to the "evaluation and feedback loop" that enterprise vendors describe only vaguely. This is a real differentiator worth productising: KB gap reports, suggested new articles and regression tests.

### Gaps
- No primary official Agentforce pricing page was fetched, so the figures are third-party.
- Microsoft Learn's per-feature language list (Arabic support) was not fetched ([copilot-agents-region-language-availability](https://learn.microsoft.com/en-us/dynamics365/business-central/copilot-agents-region-language-availability) not retrieved).
- Little was found on mobile and voice parity across these copilots, beyond Odoo 20 voice dictation and Zoho ASR being English and Hindi only.
- No source detailed Teams or Slack channel deployment of the ERP copilots. That is a known Microsoft and Salesforce pattern, but it is not cited here.

## 4. Arabic/English Middle-East specific ideas and evidence of demand

### Takeaway
Demand for Arabic WhatsApp AI in KSA and the UAE is strongly signalled, though mostly by vendors. The signals are high WhatsApp penetration, many Saudi WhatsApp-AI vendors, Gulf-dialect and Arabic-English code-switching as recurring requirements, PDPL consent rules, and Arabic voice AI on WhatsApp launched in 2025. Odoo's native agents don't bridge to WhatsApp (a third-party app exists to do it), and no Odoo app combines Arabic WhatsApp AI with ZATCA guidance. That combination is open whitespace for vitabot.

### Cited Findings
- Saudi Arabia has about 29M WhatsApp users (about 73% penetration). The UAE has 9.5M or more (95% of internet users). — [ChatDaddy (vendor, citing DemandSage 2025)](https://chatdaddy.tech/blog/whatsapp-chatbot-saudi); [ChatDaddy Dubai](https://www.chatdaddy.tech/blog/whatsapp-chatbot-dubai)
- A 2024 report argues WhatsApp will become the Middle East's customer service channel of choice. — [Algomo: Arabic automated customer service report](https://algomo.com/post/arabic-automated-customer-service-report)
- Bots need to handle colloquial phrasing, typos and **Arabic–English code-switching in a single message**. — [Logiolegion (vendor)](https://logiolegion.com/blogs/ai-chatbot-development-saudi-arabia-whatsapp-arabic-nlp-pdpl-2026); also [ChatDaddy Dubai](https://www.chatdaddy.tech/blog/whatsapp-chatbot-dubai)
- Dialect guidance: use Gulf (Khaleeji) Arabic for casual service and greetings in KSA, UAE and Qatar. — [LetsBot dialects guide 2026](https://letsbot.net/en/blogs/whatsapp-bot-arabic-dialects-guide-2026.html)
- Saudi PDPL (enforced by SDAIA) requires explicit consent before collecting customer data through WhatsApp. — [go4whatsup (vendor)](https://www.go4whatsup.com/saudi-arabia/)
- WideBot launched Arabic voice AI for WhatsApp Business calls (Oct 2025), hosted locally in KSA, UAE and Egypt. — [Sharikat Mubasher](https://www.sharikatmubasher.com/media-hub/news/21511395/widebot-ai-unveils-groundbreaking-arabic-voice-ai-for-whatsapp-business?lang=en); [FintechGate](https://fintechgate.net/?p=163880)
- ZATCA: Odoo's native `l10n_sa_edi` covers ZATCA Phase 2 (CSR and OTP onboarding flow). Odoo does **not** compute Zakat automatically. — [ECOSIRE Odoo Saudi guide 2026](https://ecosire.com/blog/odoo-saudi-arabia-localization-guide-2026)
- WhatsApp bots don't generate invoices themselves but can trigger a workflow that creates a ZATCA-compliant invoice in Odoo, Zoho Books or QuickBooks. — [automation-ksa.com](https://automation-ksa.com/en/blog/whatsapp-bot-for-business)
- Saudi Odoo partner Metch sells WhatsApp-on-Odoo integration with Arabic and English setup, training and support. This is a services offering. — [Metch](https://www.metch.sa/en/apps/whatsapp)
- The native Odoo 19 agent framework "only works inside the web interface, with no bridge to WhatsApp", which created the need for the suite_whatsapp_ai bridge app. — [apps.odoo.com: suite_whatsapp_ai](https://apps.odoo.com/apps/modules/19.0/suite_whatsapp_ai)
- Zoho's in-house ASR supports only English and Hindi, so there is a gap in Arabic voice among enterprise copilots. — [Futurum Group](https://futurumgroup.com/insights/zoho-unveils-zia-llm-no%E2%80%91code-agent-studio-and-open-agent-interoperability/)
- UAE-based vendors are active in Odoo AI governance, for example Faceela FZE LLC's governed MCP server. — [apps.odoo.com search](https://apps.odoo.com/apps/modules/browse?search=AI%20assistant&order=Downloads)

### Inferences
- High-fit vitabot ideas for the region:
  - A WhatsApp Business channel with SSO or phone-number-to-Odoo-user binding, human handoff into the existing support tickets, and PDPL consent capture.
  - Dialect-robust Arabic: detecting Gulf, Egyptian and Levantine dialects and code-switching, and answering in the user's register.
  - RTL-correct rendering of mixed Arabic/English text, numbers and record names.
  - An Arabic voice-note input on WhatsApp, with transcription.
  - A curated "ZATCA/e-invoicing FAQ" KB pack: Phase 2 onboarding steps, CSR/OTP errors, the fact that Zakat is not automated, and VAT setup.
  - Arabic-first analytics: top questions and no-info rates broken down by language and dialect.
- Because Odoo's native AI does not document Arabic or dialect handling, vitabot can claim Arabic-quality leadership if it measures it, for example with an Arabic eval set reported in admin analytics.

### Gaps
- No primary, non-vendor statistics (for example CST, TRA or GSMA) were found on WhatsApp customer-service usage or Arabic chatbot demand.
- No evidence was found of Odoo users specifically requesting ZATCA questions from a chatbot. The demand is inferred from ZATCA complexity and partner guides.
- Native Odoo AI quality in Arabic was not tested or documented.

## 5. Common complaints and limitations of Odoo AI chatbots

### Takeaway
Documented complaints centre on four things:
- **Cost and pricing opacity:** IAP credits with unpublished per-run rates, agents consuming credits while unattended, and the Standard-to-Custom upsell.
- **Edition lock-in:** Community users find the AI menus inert.
- **Configuration fragility:** prompt or agent linkage errors, API key errors, and record rules blocking agents.
- **Permission and write risk:** the safety burden now falls on permission settings and data quality.

No independent, Odoo-specific hallucination-on-numbers incident reports were found, though vendors market against it ("never hallucinated numbers"). Reddit was not reachable through the search tools.

### Cited Findings
- Cost opacity: "Two weeks after Odoo Experience and i still cant tell you if AI in Odoo 20 costs credits or not" — one LinkedIn post. — [LinkedIn (Brian Riviere repost)](https://be.linkedin.com/in/brian-riviere)
- Odoo states credit use "varies based on the specific AI feature, task complexity, and the size of your request". Scheduled and triggered agents consume credits even when nobody reads their output. Credits are tied to one database. — [iVenture Team](https://iventureteam.com/blog/odoo-20-ai-features-and-iap-credits-monthly-cost-breakdown/)
- A third-party analysis gives no universal price per accepted workflow and advises budgeting credit spend separately from review and correction labour. — [Wavect: Odoo AI cost per accepted workflow](https://wavect.io/blog/odoo-ai-cost-per-accepted-workflow/)
- Upsell: the AI app on Standard "automatically triggers an upsell" to Custom. — [Odoo 20 docs: AI](https://www.odoo.com/documentation/20.0/applications/productivity/ai.html)
- Community disappointment: a founder installed Community expecting AI from the Odoo 19 demos and found none, with AI menus "inert or absent". Community forks importing Enterprise AI modules are not production-ready. Data leaves Odoo infrastructure on every AI call, which raises data-residency objections. — [ERPClaw (competitor-biased)](https://www.erpclaw.ai/blog/odoo-enterprise-ai-pricing-2026/)
- Config errors: "AI not reachable / AI Agent not found" happens when default prompts aren't linked to an agent. — [Odoo forum, 2025-12-19](https://www.odoo.com/hi_IN/forum/help-1/how-to-solve-the-odoo-ai-access-error-ai-not-reachable-ai-agent-not-found-date-of-writing-ymd-20251219-294317). "No API key set for provider 'openai'" appears even after adding a Gemini key. — [Odoo forum, cited by iVenture Team](https://iventureteam.com/blog/odoo-20-ai-features-and-iap-credits-monthly-cost-breakdown/)
- Permissions: a record rule on res.partner restricted an AI agent's access for a particular group. — [Odoo forum](https://www.odoo.com/fi_FI/forum/apua-1/providing-access-of-ai-agent-to-particular-group-281570)
- Write risk: with agent write access in v20, "the project's weight" shifts to permission settings and data quality, so limits must be set deliberately. An "Auto-Approve Actions" option skips previews. — [Macopedia](https://macopedia.com/en/blog/news/odoo-20-whats-new); [iVenture Team](https://iventureteam.com/blog/odoo-20-ai-features-and-iap-credits-monthly-cost-breakdown/)
- Vendor guidance is to enforce limits at user permissions and to block bulk or high-risk changes. — [DeployMonkey](https://deploymonkey.com/blog/ai-agent-for-odoo-permission-audit); [Pronexo: challenges of AI agents in Odoo](https://www.pronexo.com/en/blog/odoo-erp-18/challenges-of-ai-agents-odoo-erp-590)
- LLMs confusing Odoo versions is a known issue raised at OXP 2025, in the development context. — [OXP 2025 track: Beyond code generation](https://www.odoo.com/event/odoo-experience-2025-6601/track/beyond-code-generation-integrating-ai-into-odoos-development-lifecycle-lessons-learned-7931)
- Quality depends on configuration: output quality is driven by how topics, tools and sources are set up. — [Glorium Tech](https://gloriumtech.com/artificial-intelligence-in-odoo/)
- Anti-hallucination marketing: "your actual records, never hallucinated numbers". — [Claudoo](https://cicdoo.com/claudoo); Salesforce frames hallucinations as mostly a data-quality problem. — [SalesforceBen](https://www.salesforceben.com/are-agentforce-hallucinations-a-problem-or-is-it-just-your-bad-data/)
- Native chat retention is only 30 days. — [Odoo 20 release notes](https://www.odoo.com/odoo-20-release-notes)

### Inferences
- Positioning opportunities for vitabot:
  - transparent, flat or per-tenant pricing, with a cost dashboard and caps (Kalvyai already offers monthly cost limits);
  - works on Community and the Standard plan;
  - long-term conversation analytics beyond 30 days;
  - "numbers only from tools, never from the LLM": numeric answers must come from a tool or query result, shown with a source citation or deep-link;
  - safe defaults for writes: no auto-approve by default, a bulk-change block and a read-only switch per tenant.
- Vitabot's existing "weak/no-info answer" detection is directly relevant to the hallucination complaint. It can be marketed as "the bot says when it doesn't know, and admins see it", which mirrors Odoo's own live chat "don't guess" behaviour.

### Gaps
- Reddit r/Odoo, G2 and Capterra reviews of Odoo AI were not retrieved, because searches returned no Reddit threads. First-hand user sentiment is therefore under-represented.
- No quantified hallucination or accuracy benchmark of Odoo's native agents was found.
- No documented case of permission leakage, meaning an Odoo AI agent exposing data beyond the user's ACL, was found.
