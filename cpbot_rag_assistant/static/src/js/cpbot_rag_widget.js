/** @odoo-module **/

import { Component, useState, onWillStart, onPatched, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * Native chat widget for the general-purpose RAG document Q&A assistant.
 *
 * Config (backend URL + Bearer token) is never hardcoded here: it is
 * fetched at startup from ir.config_parameter, where it was stored by
 * res.config.settings (see models/res_config_settings.py).
 *
 * The "sources" field returned by the backend is intentionally never
 * rendered anywhere in this widget, per product requirements.
 *
 * conversation_id is kept in component state only (not persisted), so a
 * page reload always starts a fresh conversation.
 */
export class CpbotRagWidget extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.messagesRef = useRef("messagesContainer");

        this.state = useState({
            messages: [],
            inputText: "",
            loading: false,
            error: null,
            configReady: false,
            configError: null,
            conversationId: null,
        });

        this.apiUrl = "";
        this.apiToken = "";

        onWillStart(async () => {
            await this._loadConfig();
        });

        onPatched(() => {
            this._scrollToBottom();
        });
    }

    async _loadConfig() {
        try {
            const [url, token] = await Promise.all([
                this.rpc("/web/dataset/call_kw", {
                    model: "ir.config_parameter",
                    method: "get_param",
                    args: ["cpbot_rag_assistant.api_url"],
                    kwargs: {},
                }),
                this.rpc("/web/dataset/call_kw", {
                    model: "ir.config_parameter",
                    method: "get_param",
                    args: ["cpbot_rag_assistant.api_token"],
                    kwargs: {},
                }),
            ]);

            this.apiUrl = (url || "").replace(/\/+$/, "");
            this.apiToken = token || "";

            if (!this.apiUrl || !this.apiToken) {
                this.state.configError = _t(
                    "RAG Assistant is not configured yet. Ask an administrator to set the " +
                        "API URL and token under Settings > RAG Assistant."
                );
            }
        } catch (error) {
            this.state.configError = _t("Failed to load RAG Assistant configuration.");
        } finally {
            this.state.configReady = true;
        }
    }

    _scrollToBottom() {
        const el = this.messagesRef.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }

    onInputChange(ev) {
        this.state.inputText = ev.target.value;
    }

    onInputKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    async sendMessage() {
        const question = this.state.inputText.trim();
        if (!question || this.state.loading || this.state.configError) {
            return;
        }

        this.state.messages.push({ role: "user", content: question, media: null });
        this.state.inputText = "";
        this.state.error = null;
        this.state.loading = true;

        try {
            const response = await fetch(`${this.apiUrl}/ask`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${this.apiToken}`,
                },
                body: JSON.stringify({
                    question,
                    conversation_id: this.state.conversationId || null,
                    category_id: null,
                }),
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.conversation_id) {
                this.state.conversationId = data.conversation_id;
            }

            this.state.messages.push({
                role: "assistant",
                content: data.answer || "",
                media: data.media || null,
            });
        } catch (error) {
            this.state.error = _t(
                "Something went wrong while contacting the RAG Assistant. Please try again."
            );
        } finally {
            this.state.loading = false;
        }
    }
}

CpbotRagWidget.template = "cpbot_rag_assistant.ChatWidget";

registry.category("actions").add("cpbot_rag_assistant.chat_widget", CpbotRagWidget);
