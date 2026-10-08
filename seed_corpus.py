import os
from pathlib import Path
import fitz  # PyMuPDF
from backend.ingestion.pipeline import ingest_pdf

corpus_dir = Path(r"C:\Users\Sanjay\.gemini\antigravity\scratch\lexground\data\corpus")
corpus_dir.mkdir(parents=True, exist_ok=True)

# 1. Case 1: Bail Order PDF
pdf1_path = corpus_dir / "case1_bail_order.pdf"
doc1 = fitz.open()

# Page 1
page1 = doc1.new_page()
text_p1 = """IN THE HIGH COURT OF DELHI AT NEW DELHI
BAIL APPLN. NO. 1420 OF 2024
DATED: 15TH MARCH 2024
CORAM: HON'BLE MR. JUSTICE SURESH KUMAR KAIT

IN THE MATTER OF:
VIKRAM SHARMA ... PETITIONER
VERSUS
STATE (NCT OF DELHI) ... RESPONDENT

ORDER
1. This is an application filed under Section 439 of the Code of Criminal Procedure, 1973 (CrPC) for grant of regular bail in FIR No. 84/2024 registered at Police Station Connaught Place for offences punishable under Section 420, Section 468, and Section 471 of the Indian Penal Code (IPC).
2. The brief facts according to the prosecution are that the complainant lodged a complaint alleging misrepresentation and manipulation of financial records amounting to Rs. 45,00,000/-.
3. Learned Senior Counsel for the Petitioner submits that the applicant was arrested on 24-Jan-2024 and has been in judicial custody since then.
"""
page1.insert_text((50, 60), text_p1, fontsize=11)

# Page 2
page2 = doc1.new_page()
text_p2 = """4. It is further submitted that the investigation in the present FIR has reached finality and the charge sheet has already been filed before the learned Chief Metropolitan Magistrate on 10-March-2024. Therefore, custodial interrogation of the applicant is no longer required.
5. In Satender Kumar Antil v. CBI (2022) 10 SCC 51, the Hon'ble Supreme Court reiterated that bail is the rule and jail is the exception. Where investigation is complete, pre-trial detention cannot be punitive.
6. The respondent opposes bail stating that the allegations are serious, but concedes that forensic audit records have already been seized.
"""
page2.insert_text((50, 60), text_p2, fontsize=11)

# Page 3
page3 = doc1.new_page()
text_p3 = """7. Considering the totality of circumstances, the period of custody from 24-Jan-2024, the filing of the charge sheet, and adhering to the mandate of Article 21 of the Constitution of India, this Court is inclined to grant bail to the applicant.
8. Accordingly, the petitioner Vikram Sharma is directed to be released on regular bail subject to furnishing a personal bond in the sum of Rs. 50,000/- with one local surety of the like amount.
9. Bail application stands disposed of.
"""
page3.insert_text((50, 60), text_p3, fontsize=11)
doc1.save(str(pdf1_path))
doc1.close()

# 2. Case 2: Appeal Judgment PDF
pdf2_path = corpus_dir / "case2_appeal_judgment.pdf"
doc2 = fitz.open()

# Page 1
p1_d2 = doc2.new_page()
text2_p1 = """IN THE SUPREME COURT OF INDIA
CRIMINAL APPELLATE JURISDICTION
CRIMINAL APPEAL NO. 412 OF 2024
DATE: 20TH FEBRUARY 2024
BENCH: HON'BLE MR. JUSTICE B.R. GAVAI & HON'BLE MR. JUSTICE SANDEEP MEHTA

ANIL KUMAR ... APPELLANT
VERSUS
STATE OF RAJASTHAN ... RESPONDENT

JUDGMENT
1. The present appeal arises out of the final judgment and order passed by the High Court of Judicature for Rajasthan in Criminal Misc. Bail Application No. 9102/2023.
2. The appellant stands charged for offences under Section 302 and Section 34 of the Indian Penal Code. The incident occurred on 12-Nov-2022 outside village square.
"""
p1_d2.insert_text((50, 60), text2_p1, fontsize=11)

# Page 2
p2_d2 = doc2.new_page()
text2_p2 = """3. In State of Rajasthan v. Balchand, Krishna Iyer J. famously observed: The basic rule is bail, not jail, except where there are circumstances suggestive of fleeing justice.
4. Co-accused Ramesh was enlarged on bail by this Court on 15-Dec-2023. The role attributed to the appellant is on parity with the co-accused.
5. In view of prolonged incarceration and parity, the appeal is allowed and regular bail is granted.
"""
p2_d2.insert_text((50, 60), text2_p2, fontsize=11)
doc2.save(str(pdf2_path))
doc2.close()

# 3. Case 3: Scanned Document with minimal direct text (triggers OCR if needed or has crisp text)
pdf3_path = corpus_dir / "case3_scanned_notice.pdf"
doc3 = fitz.open()
p1_d3 = doc3.new_page()
p1_d3.insert_text((50, 60), "LEGAL NOTICE: Under Section 138 Negotiable Instruments Act. Cheque No. 44102 Dishonoured for Rs. 2,00,000/-. Demand made within 15 days.", fontsize=11)
doc3.save(str(pdf3_path))
doc3.close()

print("Generating corpus PDFs done. Now ingesting into pipeline...")
res1 = ingest_pdf(str(pdf1_path), "doc_case1", "Vikram Sharma v. State (Bail Order)")
res2 = ingest_pdf(str(pdf2_path), "doc_case2", "Anil Kumar v. State (Supreme Court Judgment)")
res3 = ingest_pdf(str(pdf3_path), "doc_case3", "Scanned Legal Notice Sec 138")

print(f"Ingested Case 1: {res1['chunks_count']} chunks, {res1['citations_count']} citations")
print(f"Ingested Case 2: {res2['chunks_count']} chunks, {res2['citations_count']} citations")
print(f"Ingested Case 3: {res3['chunks_count']} chunks, {res3['citations_count']} citations")
