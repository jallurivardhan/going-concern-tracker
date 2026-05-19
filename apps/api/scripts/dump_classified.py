from sqlalchemy import text
from gct.database import SessionLocal
db = SessionLocal()
rows = db.execute(text(
    "SELECT c.name, c.ticker, c.cik, f.filing_date, f.accession_number,"
    "       f.form_type, gcf.severity, gcf.flag_type,"
    "       gcf.quoted_language, gcf.classification_confidence,"
    "       gcf.classifier_version, ar.audit_firm"
    " FROM going_concern_flags gcf"
    " JOIN filings f ON f.id = gcf.filing_id"
    " JOIN companies c ON c.id = gcf.company_id"
    " LEFT JOIN auditor_reports ar ON ar.filing_id = f.id"
    " ORDER BY c.name, f.filing_date DESC"
)).fetchall()
print(f"Total rows: {len(rows)}")
for r in rows:
    ticker = r.ticker or "?"
    name = (r.name or "")[:38]
    print(f"  {ticker:<6} | {name:<38} | {r.cik} | {r.filing_date} | {r.accession_number} | {r.severity:<8} | {r.audit_firm}")
db.close()
