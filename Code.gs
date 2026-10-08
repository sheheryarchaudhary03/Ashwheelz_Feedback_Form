/**
 * Ashwheelz Customer Feedback — Google Apps Script backend.
 *
 * Serves the feedback form (Index.html) as a public web page and appends
 * every submission as one row in the "Responses" sheet of the spreadsheet
 * this script is attached to. Download that sheet as Excel any time:
 *   File > Download > Microsoft Excel (.xlsx)
 */

var SHEET_NAME = 'Responses';

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('Ashwheelz Feedback')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/**
 * Called from the form with an ordered list of [columnHeader, value] pairs.
 * New headers are added automatically, so editing questions in Index.html
 * never breaks the sheet; old columns are kept.
 */
function submitFeedback(pairs) {
  if (!Array.isArray(pairs) || pairs.length === 0) {
    throw new Error('Empty submission.');
  }

  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sheet = getSheet_();
    var lastCol = sheet.getLastColumn();
    var headers = lastCol > 0 ? sheet.getRange(1, 1, 1, lastCol).getValues()[0] : [];

    var fixed = [['Submitted At', new Date()], ['Response ID', makeId_()]];
    var all = fixed.concat(pairs);

    // Add any headers the sheet does not have yet.
    var added = false;
    all.forEach(function (p) {
      if (headers.indexOf(p[0]) === -1) { headers.push(p[0]); added = true; }
    });
    if (added) {
      sheet.getRange(1, 1, 1, headers.length).setValues([headers])
        .setFontWeight('bold').setBackground('#F7931E').setFontColor('#ffffff');
      sheet.setFrozenRows(1);
    }

    var row = headers.map(function () { return ''; });
    all.forEach(function (p) {
      var v = p[1];
      // Stop spreadsheet formula injection from typed text.
      if (typeof v === 'string' && /^[=+\-@]/.test(v)) v = "'" + v;
      row[headers.indexOf(p[0])] = v;
    });
    sheet.appendRow(row);
    return { ok: true, id: row[1] };
  } finally {
    lock.releaseLock();
  }
}

function getSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
}

function makeId_() {
  var tz = Session.getScriptTimeZone();
  return 'AW-' + Utilities.formatDate(new Date(), tz, 'yyMMdd') + '-' +
    Math.random().toString(36).slice(2, 6).toUpperCase();
}

/** Adds an "Ashwheelz" menu in the spreadsheet with a quick Excel link. */
function onOpen() {
  SpreadsheetApp.getUi().createMenu('Ashwheelz')
    .addItem('Download responses as Excel', 'showExcelLink')
    .addToUi();
}

function showExcelLink() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var url = 'https://docs.google.com/spreadsheets/d/' + ss.getId() + '/export?format=xlsx';
  var html = HtmlService.createHtmlOutput(
    '<p style="font-family:sans-serif">Click to download all responses:</p>' +
    '<p><a href="' + url + '" target="_blank" style="font-family:sans-serif;font-size:16px;color:#F7931E">' +
    'Download Ashwheelz-Feedback.xlsx</a></p>').setWidth(340).setHeight(120);
  SpreadsheetApp.getUi().showModalDialog(html, 'Export to Excel');
}
