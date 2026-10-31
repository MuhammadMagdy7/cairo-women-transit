# دليل Power BI — مواصلات السيدات

## 1. الاتصال
1. **Home → Get data → Azure → Azure SQL database**
2. Server: `sql-cairo-transit-mm.database.windows.net` · Database: `cairo_transit`
3. **Data Connectivity mode: Import** (مش DirectQuery — Import بيصحّي القاعدة مرة واحدة وقت الـ refresh، فبيوفّر من الـ 100,000 vCore-seconds المجانية)
4. Authentication: **Microsoft account → Sign in** بحساب الطالب → Connect
5. لو القاعدة نايمة (auto-pause) أول محاولة ممكن تفشل — استنى دقيقة وجرّب تاني.

## 2. الجداول اللي تختارها (9)
| الجدول | ليه |
|---|---|
| `app.rides` | الـ fact الأساسي (192,692 رحلة) |
| `app.safety_reports` | البلاغات (6,763) |
| `app.riders` | الراكبات (4,000) — السن والوظيفة للـ slicers. **مش** `rides` |
| `rpt.route_priority` | ترتيب الخطوط + الأسماء العربية |
| `rpt.stop_hotspots` | المحطات + الإحداثيات للخريطة |
| `rpt.period_stage` | الـ heatmap |
| `rpt.dim_date` | التقويم |
| `rpt.vw_route_frequency` | العرض (عربيات/الفترة) |
| `gtfs.agency` | المشغّلين |

متاخدش `gtfs.shapes` (نص مليون صف، مش محتاجه في الـ visuals الأساسية).

## 3. إعادة التسمية (Model view → double-click على الاسم)
شيل الـ prefix: `app rides` → `rides`، `app safety_reports` → `safety_reports`،
`rpt route_priority` → `route_priority` ... إلخ. ملف `measures.dax` مكتوب على الأسماء دي.

## 4. العلاقات (Model view)
| من (many) | إلى (one) | ملاحظة |
|---|---|---|
| `rides[ride_date]` | `dim_date[date]` | |
| `safety_reports[report_date]` | `dim_date[date]` | |
| `rides[route_id]` | `route_priority[route_id]` | |
| `safety_reports[route_id]` | `route_priority[route_id]` | |
| `rides[board_stop_id]` | `stop_hotspots[stop_id]` | |
| `safety_reports[nearest_stop_id]` | `stop_hotspots[stop_id]` | |
| `route_priority[agency_id]` | `agency[agency_id]` | |
| `vw_route_frequency[route_id]` | `route_priority[route_id]` | |
| `rides[rider_id]` | `riders[rider_id]` | |
| `safety_reports[rider_id]` | `riders[rider_id]` | |

كلها **Single** direction. امسح أي علاقة Power BI عملها لوحده ومش في الجدول ده
(خصوصًا `safety_reports[ride_id]` ↔ `rides`، و `riders[home_stop_id]` ↔ `stop_hotspots` — الاتنين بيعملوا ambiguity).
اعمل **Mark as date table** على `dim_date` بعمود `date`.

## 5. أعمدة الترتيب
> **اللي اتعمل فعلًا في الملف:** جدول `dim_period` (calculated) مربوط بـ `rides[period]` و `period_stage[period]`، و `dim_period[period]` مترتّب بـ `period_order` — ده بيتفادى الـ circular dependency. استخدم `dim_period[period]` في الـ visuals. السكريبت في `model_additions.tmdl`.

- في `rides`: New column
  `Period Order = SWITCH(rides[period], "AM peak",1, "Midday",2, "PM peak",3, "Evening",4)`
  نفس العمود في `period_stage` (غيّر `rides[period]` لـ `period_stage[period]`).
- **فين زرار Sort by column:**
  1. روح **Table view** (أيقونة الجدول في الشريط اللي على الشمال، تحت أيقونة Report).
  2. من لوحة **Data** على اليمين، اضغط على **اسم العمود** `period` نفسه (مش على الجدول ومش على measure).
  3. فوق هيظهر تبويب **Column tools** → زرار **Sort by column** → اختار `Period Order`.
  - بديل من **Model view**: اختار العمود → لوحة **Properties** → افتح **Advanced** → **Sort by column**.
  - لو الزرار رمادي: انت مختار measure أو جدول، مش عمود.
  - لو ظهر خطأ "can't sort ... because there are values with multiple values": العمود اللي بترتّب بيه لازم يكون له قيمة واحدة لكل قيمة في `period` — `Period Order` كده فعلًا، فاتأكد إن الـ SWITCH مكتوب صح ومفيش قيمة طالعة BLANK.
- `dim_date[month_name]` → Sort by column → `month` (بنفس الخطوات).

## 6. الـ measures
افتح `measures.dax` وانسخ كل measure في جدول `_Measures`.

## 7. الصفحات
**صفحة 1 — نظرة عامة**
- Cards: Total Rides · Total Reports · Reports per 1K Rides · Riders Affected % · Avg Felt Safe
- Line chart: Reports per 1K Rides حسب `dim_date[month_name]`
- Bar chart: Reports per 1K Rides حسب `agency[agency_name]`
- Text box بالـ `Data Note` (مهم قدام اللجنة)

**صفحة 2 — الأمان**
- Matrix (heatmap): Rows `period_stage[period]`، Columns `journey_stage`، Values `reports_per_1k`
  → Conditional formatting → Background color
- Map (أو Azure Map): Latitude `stop_hotspots[stop_lat]`، Longitude `stop_lon`،
  Size `reports`، Tooltip `stop_name_ar`, `reports_per_1k_boardings`
- Donut: Total Reports حسب `safety_reports[incident_type]`
- Slicers: `rides[period]`، `agency[agency_name]`، `riders[age_group]`
- Bar: Riders Affected % حسب `riders[occupation]`

**صفحة 3 — التوصية**
- Table: `priority_rank`, `route_long_name_ar`, `agency_name_ar`, `rides`, `reports_per_1k`,
  `avg_severity`, `priority_score` — فلتر `confidence = "ok"`، Top N = 10 على `priority_score`
- Cards: Launch Share of Reports · Launch Share of Rides
- Scatter: X `rides`، Y `reports_per_1k`، Legend `priority_tier`، Size `avg_severity`
  (بيوضّح ليه الخط اتختار: ضغط عالي + خطورة عالية)
- Slicer: `priority_tier`

## 8. الحفظ
احفظ كـ `powerbi\cairo_women_transit.pbix`.
لو هتستخدم GitHub: **File → Save as → Power BI project (.pbip)** — بيطلع ملفات نص
تقدر تعمل لها version control.
