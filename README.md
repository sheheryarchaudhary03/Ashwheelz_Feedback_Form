# Ashwheelz Feedback Form: Setup (about 5 minutes, free)

Customers open one link, fill the form (no login needed), and every answer is saved
as a new row in a Google Sheet. You download that sheet as Excel whenever you want.

## 1. Create the response sheet
1. Go to https://sheets.new (signed in with your Ashwheelz Google account).
2. Name it **Ashwheelz Feedback Responses**.

## 2. Add the form code
1. In the sheet: **Extensions → Apps Script**.
2. Delete everything in `Code.gs`, then paste the full contents of **Code.gs** from this folder.
3. Click **+** next to *Files* → **HTML** → name it exactly `Index` (it becomes `Index.html`).
4. Delete its contents and paste the full contents of **Index.html** from this folder.
5. Press **Save** (disk icon).

## 3. Publish the link
1. Click **Deploy → New deployment**.
2. Gear icon → **Web app**.
3. Set **Execute as: Me** and **Who has access: Anyone**.
4. Click **Deploy**, then **Authorize access** and allow it (Google shows an
   "unverified app" warning because it is your own script: click *Advanced → Go to project*).
5. Copy the **Web app URL**. That is the link you send to customers
   (WhatsApp, SMS, email, or print it as a QR code on delivery slips).

## 4. Download responses as Excel
- In the Google Sheet: **File → Download → Microsoft Excel (.xlsx)**, or
- Use the **Ashwheelz → Download responses as Excel** menu (appears after reloading the sheet).

## Changing questions later
Edit the `SECTIONS` list near the bottom of `Index.html` (in Apps Script), save, then
**Deploy → Manage deployments → Edit (pencil) → Version: New version → Deploy**.
The link stays the same. New questions get new columns automatically; old data is kept.

## Files in this folder
- `Code.gs`: saves responses to the sheet
- `Index.html`: the form customers see (logo already embedded)
- `src/`: editable source (`form.template.html` + `logo.webp`) used to rebuild `Index.html`
