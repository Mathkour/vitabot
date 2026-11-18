# Ask Odoo: claude-sonnet-5 vs gemini-2.5-flash

14 questions, run 2026-11-14 16:14. Costs are estimates from token counts.

| | Sonnet | Flash |
|---|---|---|
| Avg cost / question | $0.0149 | $0.0041 |
| Per 1,000 questions | $15 | $4 |
| Avg latency | 10.9s | 5.8s |
| Errors | 0 | 0 |
| Charts shown | 6 | 4 |

Mark each question: Same / Sonnet better / Flash better / Both wrong. Check numbers against Odoo.

## 1. What is our total revenue this month?

| | Sonnet | Flash |
|---|---|---|
| Answer | I don't have a tool that computes revenue aggregated specifically for a date range like "this month" — the verified summary I have is the overall total revenue across all orders (411,101.02), not broken down by month. Raw order/invoice listings are capped at a limited number of records, so summing from those would not give an accurate total and could be misleading.<br><br>If it helps, I can pull a list of this month's individual orders or invoices (Nov 1–14, 2026) for you to review, but I can't give you a verified "total revenue this month" figure with the tools currently available. Would you like me to list this month's orders/invoices instead? | I can give you the overall total revenue, which is 411,101.02. I do not have the ability to calculate the total revenue for a specific month. |
| Tools | - | - |
| Chart | no | no |
| Rounds / time | 1 / 19.9s | 1 / 15.8s |
| Cost | $0.0239 | $0.0034 |

Verdict: 

## 2. كم عدد الطلبات اليوم؟

| | Sonnet | Flash |
|---|---|---|
| Answer | لا توجد أي طلبات مسجلة اليوم (2026-11-14). | إجمالي عدد الطلبات هو 56. |
| Tools | search_orders | - |
| Chart | no | no |
| Rounds / time | 2 / 5.2s | 1 / 1.0s |
| Cost | $0.0076 | $0.0016 |

Verdict: 

## 3. Who are the top 5 customers this year?

| | Sonnet | Flash |
|---|---|---|
| Answer | Here are the top 5 customers by total spend (overall figures, as our system tracks lifetime totals rather than a separate "this year" breakdown):<br><br>1. شركة امواج الطبية — 164,281.23<br>2. صيدلية زهرة الاندلس الطبية — 43,972.50<br>3. ورقان للمستلزمات الطبية — 39,920.25<br>4. بيت العلاج للمستلزمات الطبية — 39,387.46<br>5. جمعية رعاية الايتام بالجموم — 37,500.00 | The top 5 customers by amount spent this year are:<br>1. شركة امواج الطبية: 164281.23<br>2. صيدلية زهرة الاندلس الطبية: 43972.5<br>3. ورقان للمستلزمات الطبية: 39920.25<br>4. بيت العلاج للمستلزمات الطبية: 39387.46<br>5. جمعية رعاية الايتام بالجموم: 37500 |
| Tools | get_top_customers > present_chart | get_top_customers > present_chart |
| Chart | yes | yes |
| Rounds / time | 3 / 10.4s | 3 / 5.5s |
| Cost | $0.0148 | $0.0055 |

Verdict: 

## 4. أفضل 10 منتجات مبيعاً هذا الشهر

| | Sonnet | Flash |
|---|---|---|
| Answer | إذا كنت تريد بيانات مقتصرة فعلياً على الشهر الحالي فقط، يمكنني البحث في الطلبات الفردية ضمن هذا النطاق الزمني باستخدام أداة البحث عن الطلبات، لكن النتائج لن تكون بنفس دقة الترتيب الإجمالي. أخبرني إذا أردت ذلك. | لقد قمت بعرض أفضل 10 منتجات مبيعاً لك. |
| Tools | get_top_products > present_chart | get_top_products > present_chart |
| Chart | yes | yes |
| Rounds / time | 3 / 15.3s | 3 / 18.2s |
| Cost | $0.0249 | $0.0077 |

Verdict: 

## 5. Show me a chart of the top products by revenue this month

| | Sonnet | Flash |
|---|---|---|
| Answer | I've displayed the chart above. A quick note: the top products tool gives overall best-sellers by revenue rather than a month-specific breakdown, so if you need figures strictly for November 2026, let me know and I can check via order/invoice listings instead, though that would require manually totaling individual records rather than a clean aggregate. | I apologize, but I cannot provide a chart of the top products by revenue for "this month" as the available tools do not support filtering product sales data by a specific date range. I can only provide the top-selling products overall. |
| Tools | get_top_products > present_chart | - |
| Chart | yes | no |
| Rounds / time | 3 / 10.4s | 1 / 2.4s |
| Cost | $0.0165 | $0.0024 |

Verdict: 

## 6. Which products are low in stock?

| | Sonnet | Flash |
|---|---|---|
| Answer | Here are the products currently lowest in stock:<br><br>1. DALACIN C 150 MG 16 CAPS — 1 unit<br>2. ZINNAT 250 MG 14 TABS — 1 unit<br>3. KLACID 250 MG 14 TABS — 1 unit<br>4. CEFIM 200 MG 8 CAPS — 1 unit<br>5. LIFREE Adult Diaper Compress X-Large 18x2 — -1 unit (oversold/negative stock, needs attention)<br>6. SWISSLAC NO 2 MILK 400GM — 2 units<br>7. ZINOXIMORE 250 MG 14 TABS — 4 units<br>8. LIFREE Adult Culotte Medium Mega 40x2 — 6 units<br>9. LIFREE Adult Culotte Large Mega 36x2 — 6 units<br>10. Fine Care Adult Diapers Large 18 pcs — 9 units<br><br>Most urgent: the LIFREE Adult Diaper Compress X-Large shows negative stock (-1), meaning it's oversold and needs immediate restocking. Several medications (DALACIN C, ZINNAT, KLACID, CEFIM) are also critically low at just 1 unit each. | Here is a list of products with 10 units or less in stock:<br><br>1.  [VG005291] DALACIN C 150 MG 16 CAPS: 1 unit<br>2.  [VG001104] ZINOXIMORE 250 MG 14 TABS: 4 units<br>3.  [VG001078] ZINNAT 250 MG 14 TABS: 1 unit<br>4.  [VG002970] KLACID 250 MG 14 TABS: 1 unit<br>5.  [VG001887] CEFIM 200 MG 8 CAPS: 1 unit<br>6.  [VG022517] LIFREE ADULT DIAPER COMPRESS X-LARGE 18×2-18263: -1 unit (out of stock)<br>7.  [VG023330] Fine Care Adult Diapers Large 18 pcs: 9 units<br>8.  [VG013458] SWISSLAC NO 2 MILK 400GM: 2 units<br>9.  [VG022523] LIFREE ADULT CULOTTE MEDIUM MEGA 40×2-17552: 6 units<br>10. [VG022521] LIFREE ADULT CULOTTE LARGE MEGA 36×2-17572: 6 units<br>11. [VG013394] FAIR&WHITE PARIS POCKET DEO 50ML: 2 units<br>12. [VG002941] KLAVOX 375 MG 20 TABS: 1 unit<br>13. مزيل العرق ازرق 50مل: 2 units<br>14. [VG001738] CLAVODAR 1 GM 14 TABS: -6 units (out of stock)<br>15. [VG022524] LIFREE ADULT CULOTTE X-LARGE 28×2-17480R: -1 unit (out of stock)<br>16. [VG008975] VICHY DEO ROLL MINERAL 48 HR BLUE 50ML: 1 unit<br>17. [VG023322] Fine Care 20 Under Pads 4*20 (60*90 Cm): -1 unit (out of stock)<br>18. [VG008418] HYMOX 250 MG 20 CAPS ملغي: 1 unit<br>19. [VG001099] ZITHROMAX 250 MG 6 CAPS: 1 unit |
| Tools | get_stock_levels > present_chart | get_stock_levels > present_chart |
| Chart | yes | yes |
| Rounds / time | 3 / 9.3s | 3 / 12.4s |
| Cost | $0.0166 | $0.0085 |

Verdict: 

## 7. كم المخزون المتوفر من بنادول؟

| | Sonnet | Flash |
|---|---|---|
| Answer | تم عرض الرسم البياني أعلاه يوضح وضع المخزون الفعلي لأصناف بنادول المختلفة في موقع QDS 5/Stock. |  |
| Tools | get_stock_levels > get_stock_levels > present_chart | get_stock_levels > present_chart |
| Chart | yes | yes |
| Rounds / time | 4 / 14.5s | 3 / 7.3s |
| Cost | $0.0235 | $0.0079 |

Verdict: 

## 8. List the unpaid invoices from last week

| | Sonnet | Flash |
|---|---|---|
| Answer | Only one invoice was issued last week (Nov 2–8, 2026): INV/2026/643362 for customer "hussein", dated 2026-11-03, total 46.00, status posted. However, its payment status is already "paid" — so there are no unpaid invoices from last week. | I found one invoice from last week:<br><br>Customer: hussein<br>Date: 2026-11-03<br>Invoice Number: INV/2026/643362<br>Payment Status: paid<br>Status: posted<br>Total: 46<br><br>This invoice has a payment status of "paid", so there are no unpaid invoices from last week. |
| Tools | search_invoices | search_invoices |
| Chart | no | no |
| Rounds / time | 2 / 18.3s | 2 / 5.6s |
| Cost | $0.0105 | $0.0051 |

Verdict: 

## 9. What are my permissions?

| | Sonnet | Flash |
|---|---|---|
| Answer | I don't have a current user identity on file for this session, so I can't automatically look up "your" permissions. Could you tell me your name or the email you're registered under in the system? I'll look up your access rights right away. | I can tell you your permissions, but I need your name first. What name should I look up? |
| Tools | - | - |
| Chart | no | no |
| Rounds / time | 1 / 3.0s | 1 / 0.9s |
| Cost | $0.0036 | $0.0016 |

Verdict: 

## 10. What access rights does the support team have?

| | Sonnet | Flash |
|---|---|---|
| Answer | The support team (support@vitacareonline.com) has an extensive set of functional access rights, including:<br><br>Administrator-level access in:<br>1. Point of Sale / Administrator<br>2. Purchase / Administrator<br>3. Inventory / Administrator<br>4. Sales / Administrator<br>5. Employees / Administrator<br><br>Invoicing and accounting:<br>6. Invoicing / Accountant<br>7. Invoicing / Billing<br>8. Invoicing / Chief Accountant<br><br>Sales:<br>9. Sales / User: All Documents<br>10. Sales / User: Own Documents Only<br><br>Pharmacy management rights:<br>11. Pharmacy Manager / Assign Users to Branches<br>12. Pharmacy Manager / Change User Password and PIN Code<br>13. Pharmacy Manager / Manage Inventory Access Right<br>14. Pharmacy Manager / Remove-Archive Users<br>15. Pharmacy Admin<br><br>Inventory related:<br>16. Inventory / Product Price Editing<br>17. Inventory / Product Quantity Editing<br>18. Inventory / User<br><br>Other operational rights:<br>19. Purchase / User<br>20. Point of Sale / User<br>21. Point of Sale / Show Cash Move Button in POS<br>22. Point of Sale / Show Sales Analysis Report<br>23. Employees / Officer<br>24. Refund Manager<br>25. Display Order Line Sequence Number<br>26. Edit SFDA Codes<br>27. User types / Internal User<br><br>Custom Vitacare group permissions:<br>28. Vitacare Groups / Hide RFQ/PO Send/Print<br>29. Vitacare Groups / POS Session Report Manager<br>30. Vitacare Groups / Show PO Sales Price<br>31. Vitacare Groups / Validate Return PO Picking<br><br>Plus a special access entry called "Access query_deluxe".<br><br>Overall, this account has very broad administrative control across Sales, Inventory, Purchase, Point of Sale, Invoicing/Accounting, Employees, and Pharmacy management areas — essentially a super-user level of functional access (though Administration/Settings and technical permissions are not visible through this tool). | The support team (support@vitacareonline.com) has the following access rights:<br><br>Access query_deluxe<br>Invoicing / Accountant<br>Point of Sale / Administrator<br>Purchase / Administrator<br>Inventory / Administrator<br>Sales / Administrator<br>Employees / Administrator<br>Pharmacy Manager / Assign Users to Branches<br>Invoicing / Billing<br>Pharmacy Manager / Change User Password and PIN Code<br>Invoicing / Chief Accountant<br>Display Order Line Sequence Number<br>Edit SFDA Codes<br>Vitacare Groups / Hide RFQ/PO Send/Print<br>User types / Internal User<br>Pharmacy Manager / Manage Inventory Access Right<br>Employees / Officer<br>Pharmacy Admin<br>Vitacare Groups / POS Session Report Manager<br>Inventory / Product Price Editing<br>Inventory / Product Quantity Editing<br>Refund Manager<br>Pharmacy Manager / Remove-Archive Users<br>Point of Sale / Show Cash Move Button in POS<br>Vitacare Groups / Show PO Sales Price<br>Point of Sale / Show Sales Analysis Report<br>Purchase / User<br>Point of Sale / User<br>Inventory / User<br>Sales / User: All Documents<br>Sales / User: Own Documents Only<br>Vitacare Groups / Validate Return PO Picking |
| Tools | get_user_access_rights | get_user_access_rights |
| Chart | no | no |
| Rounds / time | 2 / 9.1s | 2 / 3.4s |
| Cost | $0.0136 | $0.0037 |

Verdict: 

## 11. Which warehouses do we have?

| | Sonnet | Flash |
|---|---|---|
| Answer | We have 24 warehouses in total:<br><br>1. Main Warehouse (رئيسي)<br>2. المجاهدين 1 (MOJ1)<br>3. الحسينية2 (HUS2)<br>4. وادي جليل 3 (WADI3)<br>5. الشرايع 4 (SHA4)<br>6. القادسية 5 (QDS 5)<br>7. وادي جليل 6 (Wadi6)<br>8. الفردوس 7 (FRD 7)<br>9. البحيرات 8 (BOH 8)<br>10. الزايدي 9 (ZAI 9)<br>11. العوالي 10 (AWA10)<br>12. الجموم 11 (JOM11)<br>13. الحوية (HOYA)<br>14. شهار 12 (SHE12)<br>15. الشرايع-15 (SHA15)<br>16. الزاهر 14 (Zah14)<br>17. العسيلة 13 (USA13)<br>18. الراشدية 16 (RAS16)<br>19. الشرائع 17 (SHA17)<br>20. الجموم-18 (JOM18)<br>21. الجموم ١٩ (JOM19)<br>22. الشامل 16 (SHA16)<br>23. الراشدية - warehouse # 25 (cw25)<br>24. الأمير فواز13 (FAW13)<br>25. العمرة 20 (OMR20)<br><br>(Note: that's actually 25 listed entries.) | We have the following warehouses:<br>Main Warehouse<br>المجاهدين 1<br>الحسينية2<br>وادي جليل 3<br>الشرايع 4<br>القادسية 5<br>وادي جليل 6<br>الفردوس 7<br>البحيرات 8<br>الزايدي 9<br>العوالي 10<br>الجموم 11<br>الحوية<br>شهار 12<br>الشرايع-15<br>الزاهر 14<br>العسيلة 13<br>الراشدية 16<br>الشرائع 17<br>الجموم-18<br>الجموم ١٩<br>الشامل 16<br>الراشدية - warehouse # 25<br>الأمير فواز13<br>العمرة 20 |
| Tools | get_warehouses | get_warehouses |
| Chart | no | no |
| Rounds / time | 2 / 5.6s | 2 / 2.6s |
| Cost | $0.0109 | $0.0037 |

Verdict: 

## 12. Compare sales this month with last month

| | Sonnet | Flash |
|---|---|---|
| Answer | The chart above illustrates the gap: October had 8 orders worth roughly 13,615.80 in total, while November has had no orders recorded yet through November 14th. Keep in mind the month is still in progress, so this isn't a final comparison. | I cannot compare sales this month with last month using my current tools. I can provide overall sales summaries or search for specific orders/invoices, but I don't have a function to aggregate sales data for arbitrary time periods like "this month" or "last month" for direct comparison. |
| Tools | search_orders > search_orders > present_chart | - |
| Chart | yes | no |
| Rounds / time | 3 / 16.5s | 1 / 2.0s |
| Cost | $0.0247 | $0.0021 |

Verdict: 

## 13. مين أكثر عميل اشترى من أول السنة؟

| | Sonnet | Flash |
|---|---|---|
| Answer | أكثر عميل اشترى (إجمالي الإنفاق) هو شركة امواج الطبية بإجمالي 164,281.23.<br><br>ملاحظة: هذا الرقم يمثل إجمالي ما أنفقه العميل عبر كل الفترة المتوفرة في النظام، وليس لدي أداة تسمح بحساب الترتيب مقتصرًا فقط على الفترة منذ بداية السنة الحالية بدقة. إذا أردت، يمكنني عرض طلبات هذا العميل تفصيليًا منذ بداية السنة لتتأكد بنفسك. | أكثر عميل اشترى من أول السنة هو شركة امواج الطبية بمبلغ 164281.23. |
| Tools | get_top_customers | - |
| Chart | no | no |
| Rounds / time | 2 / 12.3s | 1 / 3.1s |
| Cost | $0.0137 | $0.0028 |

Verdict: 

## 14. How do I create a new sales order?

| | Sonnet | Flash |
|---|---|---|
| Answer | I don't have specific company manual guidance provided here on creating a new sales order, so I can't give you exact verified steps for your setup. I'd recommend asking in the main chat assistant for precise guidance on this. | I don't have specific guidance on how to create a new sales order in Odoo in my current instructions. You may want to ask the main chat assistant for help with this procedural question. |
| Tools | - | - |
| Chart | no | no |
| Rounds / time | 1 / 2.7s | 1 / 1.0s |
| Cost | $0.0036 | $0.0017 |

Verdict: 

