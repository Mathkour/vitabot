/** @odoo-module **/

import { Component, useState, onWillStart, onPatched, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

/**
 * Native chat widget for the Vita Care "cpbot" assistant.
 *
 * Config (backend URL + Bearer token) is never hardcoded here: it is
 * fetched at startup from ir.config_parameter, where it was stored by
 * res.config.settings (see models/res_config_settings.py).
 *
 * Chart rendering assumption: Odoo 15's backend bundles Chart.js only for
 * the graph view (web/static/lib/Chart), and there is no stable public JS
 * hook to reuse it from an arbitrary Owl component without extra coupling.
 * To keep this module dependency-free and robust, chart payloads
 * ({type, labels, data}) are rendered as a simple label/value table
 * instead of an actual bar/line chart.
 */
export class CpbotChatWidget extends Component {
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
                    args: ["cpbot_vita_insights.api_url"],
                    kwargs: {},
                }),
                this.rpc("/web/dataset/call_kw", {
                    model: "ir.config_parameter",
                    method: "get_param",
                    args: ["cpbot_vita_insights.api_token"],
                    kwargs: {},
                }),
            ]);

            this.apiUrl = (url || "").replace(/\/+$/, "");
            this.apiToken = token || "";

            if (!this.apiUrl || !this.apiToken) {
                this.state.configError = _t(
                    "Vita Insights is not configured yet. Ask an administrator to set the " +
                        "API URL and token under Settings > Vita Insights."
                );
            }
        } catch (error) {
            this.state.configError = _t("Failed to load Vita Insights configuration.");
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

        const history = this.state.messages.map((message) => ({
            role: message.role,
            content: message.content,
        }));

        this.state.messages.push({ role: "user", content: question, chart: null });
        this.state.inputText = "";
        this.state.error = null;
        this.state.loading = true;

        try {
            const response = await fetch(`${this.apiUrl}/odoo/ask`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${this.apiToken}`,
                },
                body: JSON.stringify({ question, history }),
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            this.state.messages.push({
                role: "assistant",
                content: data.answer || "",
                chart: data.chart || null,
            });
        } catch (error) {
            this.state.error = _t(
                "Something went wrong while contacting Vita Insights. Please try again."
            );
        } finally {
            this.state.loading = false;
        }
    }
}

CpbotChatWidget.template = "cpbot_vita_insights.ChatWidget";

registry.category("actions").add("cpbot_vita_insights.chat_widget", CpbotChatWidget);
