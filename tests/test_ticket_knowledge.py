"""Ticket replies can teach the bot (save_to_knowledge), but only tenant
admins: the bot's knowledge is shared by the whole tenant."""
from fastapi.testclient import TestClient

import main
from core.auth import UserScope, get_current_user_id, require_admin_or_company_admin

TENANT = "11111111-1111-1111-1111-111111111111"
TICKET = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


def test_company_admin_cannot_save_ticket_answer_to_knowledge():
    main.app.dependency_overrides[require_admin_or_company_admin] = lambda: UserScope(
        tenant_id=TENANT, role="company_admin", company_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
    )
    main.app.dependency_overrides[get_current_user_id] = lambda: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    try:
        resp = TestClient(main.app).post(
            f"/support-tickets/{TICKET}/messages", json={"content": "Do X then Y.", "save_to_knowledge": True},
        )
    finally:
        main.app.dependency_overrides.clear()
    # Refused before touching the database (no DB in this test).
    assert resp.status_code == 403
