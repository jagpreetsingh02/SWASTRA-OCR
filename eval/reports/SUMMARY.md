# Evaluation summary

Generated 2026-09-13 16:15 by `eval/run.py`.

## dev / text


Documents: 20 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.994 · recall 1.0 (tp 321, fp 2, fn 0)
False positives 2 · false negatives 0 · wrong values 0 · **unflagged errors 1** · placement errors 0 · grounding failures 0

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| allergies | 3 | 0 | 0 | 1.0 | 1.0 |
| date | 19 | 0 | 0 | 1.0 | 1.0 |
| diagnoses | 15 | 0 | 0 | 1.0 | 1.0 |
| doctor_name | 12 | 0 | 0 | 1.0 | 1.0 |
| medication | 44 | 0 | 0 | 1.0 | 1.0 |
| medication.dosage | 41 | 0 | 0 | 1.0 | 1.0 |
| medication.duration | 21 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 44 | 0 | 0 | 1.0 | 1.0 |
| medication_mention | 4 | 0 | 0 | 1.0 | 1.0 |
| medication_mention.dosage | 2 | 0 | 0 | 1.0 | 1.0 |
| patient_name | 9 | 0 | 0 | 1.0 | 1.0 |
| symptoms | 12 | 0 | 0 | 1.0 | 1.0 |
| test_result | 23 | 0 | 0 | 1.0 | 1.0 |
| test_result.reference_range | 19 | 0 | 0 | 1.0 | 1.0 |
| test_result.unit | 22 | 0 | 0 | 1.0 | 1.0 |
| test_result.value | 23 | 0 | 0 | 1.0 | 1.0 |
| tests | 8 | 2 | 0 | 0.8 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| discharge.txt | ok | 9/0/0 | 0 |  |  | — |
| discharge_copd.txt | ok | 19/0/0 | 0 |  |  | — |
| hw_rx_bradley.txt | ok | 18/0/0 | 0 |  |  | — |
| hw_rx_brush_hard.txt | ok | 11/0/0 | 0 |  |  | — |
| hw_rx_chalkboard.txt | ok | 14/0/0 | 0 |  |  | — |
| hw_rx_cursive.txt | ok | 15/0/0 | 0 |  |  | — |
| hx_lab_biochem.txt | ok | 26/1/0 | 1 |  |  | false_positive tests: expected None got 'ALT' (**NOT flagged**) |
| hx_mixed_paed.txt | ok | 18/0/0 | 0 |  |  | — |
| invoice_pharmacy_gst.txt | ok | 5/0/0 | 0 |  |  | — |
| lab_haematology_table.txt | ok | 26/0/0 | 0 |  |  | — |
| lab_report.txt | ok | 29/0/0 | 0 |  |  | — |
| mixed_printed_handwritten.txt | ok | 15/0/0 | 0 |  |  | — |
| nonmedical_invoice.txt | ok | 1/0/0 | 0 |  |  | — |
| pharma_info_minipress_letter.txt | ok | 2/0/0 | 0 |  |  | — |
| prescription.txt | ok | 21/0/0 | 0 |  |  | — |
| prescription_handwritten.txt | ok | 15/0/0 | 0 |  |  | — |
| probe_false_positives.txt | ok | 15/1/0 | 0 |  |  | false_positive tests: expected None got 'SpO2' (flagged) |
| probe_medication_formats.txt | ok | 24/0/0 | 0 |  |  | — |
| rx_clinic_uti.txt | ok | 22/0/0 | 0 |  |  | — |
| rx_paediatric_opd.txt | ok | 16/0/0 | 0 |  |  | — |

## dev / ocr


Documents: 20 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.979 · recall 0.982 (tp 322, fp 7, fn 6)
False positives 6 · false negatives 5 · wrong values 1 · **unflagged errors 1** · placement errors 0 · grounding failures 0

OCR critical tokens: accuracy 0.984 (date 18/19 · dosage 44/44 · duration 28/28 · frequency 43/43 · header 15/15 · lab_name 26/28 · lab_value 32/32 · medicine_name 46/47)
OCR mean CER 0.0059 · unsupported (invented/garbled) lines 0 · mean 14.13 s/file
Output distinctness (closest to its own source): 20/20

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| allergies | 1 | 0 | 0 | 1.0 | 1.0 |
| date | 18 | 1 | 1 | 0.947 | 0.947 |
| diagnoses | 15 | 2 | 2 | 0.882 | 0.882 |
| doctor_name | 11 | 0 | 0 | 1.0 | 1.0 |
| medication | 42 | 1 | 1 | 0.977 | 0.977 |
| medication.dosage | 40 | 0 | 0 | 1.0 | 1.0 |
| medication.duration | 27 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 42 | 0 | 0 | 1.0 | 1.0 |
| medication_mention | 4 | 0 | 0 | 1.0 | 1.0 |
| medication_mention.dosage | 2 | 0 | 0 | 1.0 | 1.0 |
| patient_name | 4 | 0 | 0 | 1.0 | 1.0 |
| symptoms | 8 | 0 | 0 | 1.0 | 1.0 |
| test_result | 26 | 2 | 2 | 0.929 | 0.929 |
| test_result.reference_range | 25 | 0 | 0 | 1.0 | 1.0 |
| test_result.unit | 25 | 0 | 0 | 1.0 | 1.0 |
| test_result.value | 26 | 0 | 0 | 1.0 | 1.0 |
| tests | 6 | 1 | 0 | 0.857 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| discharge.pdf | ok | 9/0/0 | 0 | 8/8 | 0.0 | — |
| discharge_degraded.png | ok | 9/0/0 | 0 | 8/8 | 0.0 | — |
| discharge_scan.png | ok | 9/0/0 | 0 | 8/8 | 0.0 | — |
| hw_rx_bradley.png | low_confidence | 18/0/0 | 0 | 14/14 | 0.0 | OCR read 'Rx' as 'RX' |
| hw_rx_brush_hard.png | ok | 10/1/1 | 0 | 9/10 | 0.031 | wrong_value date: expected '30/05/2026' got '30|05|2026' (flagged)<br>OCR missed date '30/05/2026'<br>OCR read '30/05/2026' as '30|05|2026'<br>OCR read '50mcg' as '50 mcg' |
| hw_rx_chalkboard.png | ok | 14/0/0 | 0 | 12/12 | 0.0 | — |
| hw_rx_cursive.png | ok | 13/2/2 | 0 | 11/11 | 0.031 | missing diagnoses: expected 'T2DM' got None<br>missing diagnoses: expected 'HTN' got None<br>false_positive diagnoses: expected None got 'T2D' (flagged)<br>false_positive diagnoses: expected None got 'H T N' (flagged)<br>OCR read 'T2DM, HTN' as 'T2D.M, H T N'<br>OCR read 'Adv:' as 'Ado:' |
| hx_lab_biochem.png | ok | 26/1/0 | 1 | 15/15 | 0.0 | false_positive tests: expected None got 'ALT' (**NOT flagged**) |
| hx_mixed_paed.png | ok | 18/0/0 | 0 | 15/15 | 0.0 | — |
| invoice_pharmacy_gst.png | ok | 5/0/0 | 0 | 5/5 | 0.0 | — |
| lab_report.pdf | ok | 29/0/0 | 0 | 16/16 | 0.0 | — |
| lab_report_degraded.png | ok | 25/1/1 | 0 | 15/16 | 0.003 | missing test_result: expected 'HbA1c' got None<br>false_positive test_result: expected None got 'HbAlc' (flagged)<br>OCR missed lab_name 'HbA1c'<br>OCR read 'HbA1c' as 'HbAlc' |
| lab_report_scan.png | ok | 25/1/1 | 0 | 15/16 | 0.003 | missing test_result: expected 'HbA1c' got None<br>false_positive test_result: expected None got 'HbAlc' (flagged)<br>OCR missed lab_name 'HbA1c'<br>OCR read 'HbA1c' as 'HbAlc' |
| mixed_printed_handwritten.png | ok | 15/0/0 | 0 | 13/13 | 0.0 | — |
| pharma_info_minipress_letter.png | ok | 2/0/0 | 0 | 2/2 | 0.037 | OCR read 'finally cooled down.' as 'fina' |
| prescription.pdf | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |
| prescription_degraded.png | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |
| prescription_handwritten.png | ok | 11/1/1 | 0 | 14/15 | 0.013 | missing medication: expected 'Augmtin' got None<br>false_positive medication: expected None got 'Augmentin' (flagged)<br>OCR missed medicine_name 'Augmtin'<br>OCR read 'Rx' as 'RX'<br>OCR read 'Augmtin' as 'Augmentin' |
| prescription_photo_handheld.jpg | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |
| prescription_scan.png | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |

## heldout / text


Documents: 7 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.952 · recall 0.952 (tp 140, fp 7, fn 7)
False positives 5 · false negatives 5 · wrong values 2 · **unflagged errors 6** · placement errors 0 · grounding failures 0

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| allergies | 1 | 2 | 0 | 0.333 | 1.0 |
| date | 6 | 1 | 1 | 0.857 | 0.857 |
| diagnoses | 6 | 0 | 0 | 1.0 | 1.0 |
| doctor_name | 6 | 0 | 0 | 1.0 | 1.0 |
| medication | 14 | 0 | 0 | 1.0 | 1.0 |
| medication.dosage | 11 | 1 | 1 | 0.917 | 0.917 |
| medication.duration | 5 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 13 | 0 | 1 | 1.0 | 0.929 |
| patient_name | 6 | 0 | 0 | 1.0 | 1.0 |
| symptoms | 3 | 0 | 0 | 1.0 | 1.0 |
| test_result | 18 | 0 | 0 | 1.0 | 1.0 |
| test_result.reference_range | 16 | 0 | 2 | 1.0 | 0.889 |
| test_result.unit | 16 | 0 | 2 | 1.0 | 0.889 |
| test_result.value | 18 | 0 | 0 | 1.0 | 1.0 |
| tests | 1 | 3 | 0 | 0.25 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| hx_discharge_kmc.txt | ok | 19/1/0 | 1 |  |  | false_positive tests: expected None got 'chest X-ray' (**NOT flagged**) |
| hx_lab_cbc.txt | ok | 25/1/2 | 1 |  |  | missing test_result.unit: expected 'mill/cumm' got None<br>missing test_result.reference_range: expected '3.8 - 4.8' got None<br>false_positive tests: expected None got 'COMPLETE BLOOD COUNT' (**NOT flagged**) |
| hx_labs_2page.txt | ok | 48/2/3 | 2 |  |  | wrong_value date: expected '09/08/2026' got '21-08-2026' (**NOT flagged**)<br>missing test_result.unit: expected 'mill/cumm' got None<br>missing test_result.reference_range: expected '3.8 - 4.8' got None<br>false_positive tests: expected None got 'ALT' (**NOT flagged**) |
| hx_nonmedical_notice.txt | ok | 1/0/0 | 0 |  |  | — |
| hx_rx_hand_banerjee.txt | ok | 14/1/2 | 1 |  |  | missing medication.frequency: expected 'BBF' got None<br>wrong_value medication.dosage: expected '2 tsp' got '2' (**NOT flagged**) |
| hx_rx_hand_iqbal.txt | ok | 14/0/0 | 0 |  |  | — |
| hx_rx_printed_gp.txt | ok | 19/2/0 | 1 |  |  | false_positive allergies: expected None got 'Allergies' (**NOT flagged**)<br>false_positive allergies: expected None got 'None known' (flagged) |

## heldout / ocr


Documents: 9 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.943 · recall 0.948 (tp 183, fp 11, fn 10)
False positives 8 · false negatives 7 · wrong values 3 · **unflagged errors 7** · placement errors 0 · grounding failures 0

OCR critical tokens: accuracy 1.0 (date 9/9 · dosage 15/15 · duration 7/7 · frequency 17/17 · header 18/18 · lab_name 24/24 · lab_value 25/25 · medicine_name 17/17)
OCR mean CER 0.0238 · unsupported (invented/garbled) lines 0 · mean 16.85 s/file
Output distinctness (closest to its own source): 9/9

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| allergies | 1 | 4 | 0 | 0.2 | 1.0 |
| date | 8 | 1 | 1 | 0.889 | 0.889 |
| diagnoses | 8 | 0 | 0 | 1.0 | 1.0 |
| doctor_name | 8 | 0 | 0 | 1.0 | 1.0 |
| medication | 17 | 0 | 0 | 1.0 | 1.0 |
| medication.dosage | 14 | 1 | 1 | 0.933 | 0.933 |
| medication.duration | 7 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 16 | 0 | 1 | 1.0 | 0.941 |
| patient_name | 7 | 1 | 1 | 0.875 | 0.875 |
| symptoms | 5 | 0 | 0 | 1.0 | 1.0 |
| test_result | 24 | 0 | 0 | 1.0 | 1.0 |
| test_result.reference_range | 21 | 0 | 3 | 1.0 | 0.875 |
| test_result.unit | 21 | 0 | 3 | 1.0 | 0.875 |
| test_result.value | 24 | 0 | 0 | 1.0 | 1.0 |
| tests | 2 | 4 | 0 | 0.333 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| hx_discharge_kmc.png | ok | 18/2/1 | 2 | 16/16 | 0.0 | wrong_value patient_name: expected 'Lakshmi Iyer' got 'Lakshmi Iyer IP' (**NOT flagged**)<br>false_positive tests: expected None got 'chest X-ray' (**NOT flagged**) |
| hx_lab_cbc.png | low_confidence | 25/1/2 | 0 | 15/15 | 0.084 | missing test_result.unit: expected 'mill/cumm' got None<br>missing test_result.reference_range: expected '3.8 - 4.8' got None<br>false_positive tests: expected None got 'COMPLETE BLOOD COUNT' (flagged) |
| hx_lab_cbc_degraded.jpg | low_confidence | 25/1/2 | 0 | 15/15 | 0.084 | missing test_result.unit: expected 'mill/cumm' got None<br>missing test_result.reference_range: expected '3.8 - 4.8' got None<br>false_positive tests: expected None got 'COMPLETE BLOOD COUNT' (flagged) |
| hx_labs_2page.pdf | low_confidence | 48/2/3 | 2 | 28/28 | 0.046 | wrong_value date: expected '09/08/2026' got '21-08-2026' (**NOT flagged**)<br>missing test_result.unit: expected 'mill/cumm' got None<br>missing test_result.reference_range: expected '3.8 - 4.8' got None<br>false_positive tests: expected None got 'ALT' (**NOT flagged**) |
| hx_nonmedical_notice.png | ok | 1/0/0 | 0 | 1/1 | 0.0 | — |
| hx_rx_hand_banerjee.png | ok | 14/1/2 | 1 | 15/15 | 0.0 | missing medication.frequency: expected 'BBF' got None<br>wrong_value medication.dosage: expected '2 tsp' got '2' (**NOT flagged**) |
| hx_rx_hand_iqbal.png | ok | 14/0/0 | 0 | 12/12 | 0.0 | OCR read 'Syp' as 'syp' |
| hx_rx_printed_gp.png | ok | 19/2/0 | 1 | 15/15 | 0.0 | false_positive allergies: expected None got 'Allergies' (**NOT flagged**)<br>false_positive allergies: expected None got 'None known' (flagged) |
| hx_rx_printed_gp_photo.heic | ok | 19/2/0 | 1 | 15/15 | 0.0 | false_positive allergies: expected None got 'Allergies' (**NOT flagged**)<br>false_positive allergies: expected None got 'None known' (flagged) |

## real_world / text

- no text cases in real_world

_No documents._

## real_world / ocr

- no ocr cases in real_world

_No documents._

## Reliability

Non-documents returning `unreadable` with no entities: **7/7**

- no_document_table.jpg: pass (unreadable)
- unreadable_blurred.jpg: pass (unreadable)
- unreadable_dark.jpg: pass (unreadable)
- white_page.png: pass (unreadable)
- noise.png: pass (unreadable)
- dust.png: pass (unreadable)
- dark_object.png: pass (unreadable)

Hallucination detector (OCR stubbed with the true text plus one invented line): detected **21/25**, invented-line entities not flagged **16**, false alarms on clean text 0/25

- dev/discharge_degraded.png: detected=True unflagged_invented=0 false_alarm=False
- dev/discharge_scan.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hw_rx_bradley.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hw_rx_brush_hard.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hw_rx_chalkboard.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hw_rx_cursive.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hx_lab_biochem.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hx_mixed_paed.png: detected=True unflagged_invented=0 false_alarm=False
- dev/invoice_pharmacy_gst.png: detected=True unflagged_invented=0 false_alarm=False
- dev/lab_report_degraded.png: detected=True unflagged_invented=0 false_alarm=False
- dev/lab_report_scan.png: detected=True unflagged_invented=0 false_alarm=False
- dev/mixed_printed_handwritten.png: detected=False unflagged_invented=4 false_alarm=False
- dev/pharma_info_minipress_letter.png: detected=True unflagged_invented=0 false_alarm=False
- dev/prescription_degraded.png: detected=True unflagged_invented=0 false_alarm=False
- dev/prescription_handwritten.png: detected=True unflagged_invented=0 false_alarm=False
- dev/prescription_photo_handheld.jpg: detected=False unflagged_invented=4 false_alarm=False
- dev/prescription_scan.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_discharge_kmc.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_lab_cbc.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_lab_cbc_degraded.jpg: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_nonmedical_notice.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_rx_hand_banerjee.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_rx_hand_iqbal.png: detected=False unflagged_invented=4 false_alarm=False
- heldout/hx_rx_printed_gp.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_rx_printed_gp_photo.heic: detected=False unflagged_invented=4 false_alarm=False
