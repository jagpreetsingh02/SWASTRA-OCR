# Evaluation summary

Generated 2026-09-13 23:05 by `eval/run.py`.

## dev / text


Documents: 23 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.998 · recall 1.0 (tp 407, fp 1, fn 0)
False positives 1 · false negatives 0 · wrong values 0 · **unflagged errors 1** · placement errors 0 · grounding failures 0

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| allergies | 4 | 0 | 0 | 1.0 | 1.0 |
| date | 22 | 0 | 0 | 1.0 | 1.0 |
| diagnoses | 19 | 0 | 0 | 1.0 | 1.0 |
| doctor_name | 15 | 0 | 0 | 1.0 | 1.0 |
| medication | 51 | 0 | 0 | 1.0 | 1.0 |
| medication.dosage | 48 | 0 | 0 | 1.0 | 1.0 |
| medication.duration | 24 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 51 | 0 | 0 | 1.0 | 1.0 |
| medication_mention | 4 | 0 | 0 | 1.0 | 1.0 |
| medication_mention.dosage | 2 | 0 | 0 | 1.0 | 1.0 |
| panel | 3 | 0 | 0 | 1.0 | 1.0 |
| patient_name | 12 | 0 | 0 | 1.0 | 1.0 |
| symptoms | 14 | 0 | 0 | 1.0 | 1.0 |
| test_result | 29 | 0 | 0 | 1.0 | 1.0 |
| test_result.reference_range | 25 | 0 | 0 | 1.0 | 1.0 |
| test_result.unit | 28 | 0 | 0 | 1.0 | 1.0 |
| test_result.value | 29 | 0 | 0 | 1.0 | 1.0 |
| tests | 9 | 1 | 0 | 0.9 | 1.0 |
| vital | 6 | 0 | 0 | 1.0 | 1.0 |
| vital.unit | 6 | 0 | 0 | 1.0 | 1.0 |
| vital.value | 6 | 0 | 0 | 1.0 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| discharge.txt | ok | 9/0/0 | 0 |  |  | — |
| discharge_copd.txt | ok | 19/0/0 | 0 |  |  | — |
| hw_rx_bradley.txt | ok | 18/0/0 | 0 |  |  | — |
| hw_rx_brush_hard.txt | ok | 11/0/0 | 0 |  |  | — |
| hw_rx_chalkboard.txt | ok | 14/0/0 | 0 |  |  | — |
| hw_rx_cursive.txt | ok | 15/0/0 | 0 |  |  | — |
| hx_discharge_kmc.txt | ok | 19/1/0 | 1 |  |  | false_positive tests: expected None got 'chest X-ray' (**NOT flagged**) |
| hx_lab_biochem.txt | ok | 27/0/0 | 0 |  |  | — |
| hx_lab_cbc.txt | ok | 28/0/0 | 0 |  |  | — |
| hx_mixed_paed.txt | ok | 21/0/0 | 0 |  |  | — |
| hx_rx_printed_gp.txt | ok | 19/0/0 | 0 |  |  | — |
| invoice_pharmacy_gst.txt | ok | 5/0/0 | 0 |  |  | — |
| lab_haematology_table.txt | ok | 27/0/0 | 0 |  |  | — |
| lab_report.txt | ok | 29/0/0 | 0 |  |  | — |
| mixed_printed_handwritten.txt | ok | 18/0/0 | 0 |  |  | — |
| nonmedical_invoice.txt | ok | 1/0/0 | 0 |  |  | — |
| pharma_info_minipress_letter.txt | ok | 2/0/0 | 0 |  |  | — |
| prescription.txt | ok | 21/0/0 | 0 |  |  | — |
| prescription_handwritten.txt | ok | 15/0/0 | 0 |  |  | — |
| probe_false_positives.txt | ok | 27/0/0 | 0 |  |  | — |
| probe_medication_formats.txt | ok | 24/0/0 | 0 |  |  | — |
| rx_clinic_uti.txt | ok | 22/0/0 | 0 |  |  | — |
| rx_paediatric_opd.txt | ok | 16/0/0 | 0 |  |  | — |

## dev / ocr


Documents: 25 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.984 · recall 0.987 (tp 442, fp 7, fn 6)
False positives 6 · false negatives 5 · wrong values 1 · **unflagged errors 1** · placement errors 0 · grounding failures 0

OCR critical tokens: accuracy 0.988 (date 23/24 · dosage 54/54 · duration 33/33 · frequency 53/53 · header 27/27 · lab_name 38/40 · lab_value 44/44 · medicine_name 56/57)
OCR mean CER 0.0114 · unsupported (invented/garbled) lines 0 · mean 13.34 s/file
Output distinctness (closest to its own source): 25/25

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| allergies | 2 | 0 | 0 | 1.0 | 1.0 |
| date | 23 | 1 | 1 | 0.958 | 0.958 |
| diagnoses | 21 | 2 | 2 | 0.913 | 0.913 |
| doctor_name | 16 | 0 | 0 | 1.0 | 1.0 |
| medication | 52 | 1 | 1 | 0.981 | 0.981 |
| medication.dosage | 50 | 0 | 0 | 1.0 | 1.0 |
| medication.duration | 32 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 52 | 0 | 0 | 1.0 | 1.0 |
| medication_mention | 4 | 0 | 0 | 1.0 | 1.0 |
| medication_mention.dosage | 2 | 0 | 0 | 1.0 | 1.0 |
| panel | 3 | 0 | 0 | 1.0 | 1.0 |
| patient_name | 9 | 0 | 0 | 1.0 | 1.0 |
| symptoms | 12 | 0 | 0 | 1.0 | 1.0 |
| test_result | 38 | 2 | 2 | 0.95 | 0.95 |
| test_result.reference_range | 37 | 0 | 0 | 1.0 | 1.0 |
| test_result.unit | 37 | 0 | 0 | 1.0 | 1.0 |
| test_result.value | 38 | 0 | 0 | 1.0 | 1.0 |
| tests | 8 | 1 | 0 | 0.889 | 1.0 |
| vital | 2 | 0 | 0 | 1.0 | 1.0 |
| vital.unit | 2 | 0 | 0 | 1.0 | 1.0 |
| vital.value | 2 | 0 | 0 | 1.0 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| discharge.pdf | ok | 9/0/0 | 0 | 8/8 | 0.0 | — |
| discharge_degraded.png | ok | 9/0/0 | 0 | 8/8 | 0.0 | — |
| discharge_scan.png | ok | 9/0/0 | 0 | 8/8 | 0.0 | — |
| hw_rx_bradley.png | low_confidence | 18/0/0 | 0 | 14/14 | 0.0 | OCR read 'Rx' as 'RX' |
| hw_rx_brush_hard.png | ok | 10/1/1 | 0 | 9/10 | 0.031 | wrong_value date: expected '30/05/2026' got '30|05|2026' (flagged)<br>OCR missed date '30/05/2026'<br>OCR read '30/05/2026' as '30|05|2026'<br>OCR read '50mcg' as '50 mcg' |
| hw_rx_chalkboard.png | ok | 14/0/0 | 0 | 12/12 | 0.0 | — |
| hw_rx_cursive.png | ok | 13/2/2 | 0 | 11/11 | 0.031 | missing diagnoses: expected 'T2DM' got None<br>missing diagnoses: expected 'HTN' got None<br>false_positive diagnoses: expected None got 'T2D' (flagged)<br>false_positive diagnoses: expected None got 'H T N' (flagged)<br>OCR read 'T2DM, HTN' as 'T2D.M, H T N'<br>OCR read 'Adv:' as 'Ado:' |
| hx_discharge_kmc.png | ok | 19/1/0 | 1 | 16/16 | 0.0 | false_positive tests: expected None got 'chest X-ray' (**NOT flagged**) |
| hx_lab_biochem.png | ok | 27/0/0 | 0 | 15/15 | 0.0 | — |
| hx_lab_cbc.png | low_confidence | 28/0/0 | 0 | 15/15 | 0.084 | — |
| hx_lab_cbc_degraded.jpg | low_confidence | 28/0/0 | 0 | 15/15 | 0.084 | — |
| hx_mixed_paed.png | ok | 21/0/0 | 0 | 15/15 | 0.0 | — |
| hx_rx_printed_gp.png | ok | 19/0/0 | 0 | 15/15 | 0.0 | — |
| hx_rx_printed_gp_photo.heic | ok | 19/0/0 | 0 | 15/15 | 0.0 | — |
| invoice_pharmacy_gst.png | ok | 5/0/0 | 0 | 5/5 | 0.0 | — |
| lab_report.pdf | ok | 29/0/0 | 0 | 16/16 | 0.0 | — |
| lab_report_degraded.png | ok | 25/1/1 | 0 | 15/16 | 0.003 | missing test_result: expected 'HbA1c' got None<br>false_positive test_result: expected None got 'HbAlc' (flagged)<br>OCR missed lab_name 'HbA1c'<br>OCR read 'HbA1c' as 'HbAlc' |
| lab_report_scan.png | ok | 25/1/1 | 0 | 15/16 | 0.003 | missing test_result: expected 'HbA1c' got None<br>false_positive test_result: expected None got 'HbAlc' (flagged)<br>OCR missed lab_name 'HbA1c'<br>OCR read 'HbA1c' as 'HbAlc' |
| mixed_printed_handwritten.png | ok | 18/0/0 | 0 | 13/13 | 0.0 | — |
| pharma_info_minipress_letter.png | ok | 2/0/0 | 0 | 2/2 | 0.037 | OCR read 'finally cooled down.' as 'fina' |
| prescription.pdf | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |
| prescription_degraded.png | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |
| prescription_handwritten.png | ok | 11/1/1 | 0 | 14/15 | 0.013 | missing medication: expected 'Augmtin' got None<br>false_positive medication: expected None got 'Augmentin' (flagged)<br>OCR missed medicine_name 'Augmtin'<br>OCR read 'Rx' as 'RX'<br>OCR read 'Augmtin' as 'Augmentin' |
| prescription_photo_handheld.jpg | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |
| prescription_scan.png | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |

## heldout / text


Documents: 4 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.975 · recall 0.963 (tp 79, fp 2, fn 3)
False positives 0 · false negatives 1 · wrong values 2 · **unflagged errors 2** · placement errors 0 · grounding failures 0

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| date | 3 | 1 | 1 | 0.75 | 0.75 |
| diagnoses | 2 | 0 | 0 | 1.0 | 1.0 |
| doctor_name | 3 | 0 | 0 | 1.0 | 1.0 |
| medication | 7 | 0 | 0 | 1.0 | 1.0 |
| medication.dosage | 4 | 1 | 1 | 0.8 | 0.8 |
| medication.duration | 2 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 6 | 0 | 1 | 1.0 | 0.857 |
| patient_name | 3 | 0 | 0 | 1.0 | 1.0 |
| symptoms | 1 | 0 | 0 | 1.0 | 1.0 |
| test_result | 12 | 0 | 0 | 1.0 | 1.0 |
| test_result.reference_range | 12 | 0 | 0 | 1.0 | 1.0 |
| test_result.unit | 12 | 0 | 0 | 1.0 | 1.0 |
| test_result.value | 12 | 0 | 0 | 1.0 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| hx_labs_2page.txt | ok | 50/1/1 | 1 |  |  | wrong_value date: expected '09/08/2026' got '21-08-2026' (**NOT flagged**) |
| hx_nonmedical_notice.txt | ok | 1/0/0 | 0 |  |  | — |
| hx_rx_hand_banerjee.txt | ok | 14/1/2 | 1 |  |  | missing medication.frequency: expected 'BBF' got None<br>wrong_value medication.dosage: expected '2 tsp' got '2' (**NOT flagged**) |
| hx_rx_hand_iqbal.txt | ok | 14/0/0 | 0 |  |  | — |

## heldout / ocr


Documents: 4 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.975 · recall 0.963 (tp 79, fp 2, fn 3)
False positives 0 · false negatives 1 · wrong values 2 · **unflagged errors 2** · placement errors 0 · grounding failures 0

OCR critical tokens: accuracy 1.0 (date 4/4 · dosage 5/5 · duration 2/2 · frequency 7/7 · header 6/6 · lab_name 12/12 · lab_value 13/13 · medicine_name 7/7)
OCR mean CER 0.0115 · unsupported (invented/garbled) lines 0 · mean 16.85 s/file
Output distinctness (closest to its own source): 4/4

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| date | 3 | 1 | 1 | 0.75 | 0.75 |
| diagnoses | 2 | 0 | 0 | 1.0 | 1.0 |
| doctor_name | 3 | 0 | 0 | 1.0 | 1.0 |
| medication | 7 | 0 | 0 | 1.0 | 1.0 |
| medication.dosage | 4 | 1 | 1 | 0.8 | 0.8 |
| medication.duration | 2 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 6 | 0 | 1 | 1.0 | 0.857 |
| patient_name | 3 | 0 | 0 | 1.0 | 1.0 |
| symptoms | 1 | 0 | 0 | 1.0 | 1.0 |
| test_result | 12 | 0 | 0 | 1.0 | 1.0 |
| test_result.reference_range | 12 | 0 | 0 | 1.0 | 1.0 |
| test_result.unit | 12 | 0 | 0 | 1.0 | 1.0 |
| test_result.value | 12 | 0 | 0 | 1.0 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| hx_labs_2page.pdf | low_confidence | 50/1/1 | 1 | 28/28 | 0.046 | wrong_value date: expected '09/08/2026' got '21-08-2026' (**NOT flagged**) |
| hx_nonmedical_notice.png | ok | 1/0/0 | 0 | 1/1 | 0.0 | — |
| hx_rx_hand_banerjee.png | ok | 14/1/2 | 1 | 15/15 | 0.0 | missing medication.frequency: expected 'BBF' got None<br>wrong_value medication.dosage: expected '2 tsp' got '2' (**NOT flagged**) |
| hx_rx_hand_iqbal.png | ok | 14/0/0 | 0 | 12/12 | 0.0 | OCR read 'Syp' as 'syp' |

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
- dev/hx_discharge_kmc.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hx_lab_biochem.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hx_lab_cbc.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hx_lab_cbc_degraded.jpg: detected=True unflagged_invented=0 false_alarm=False
- dev/hx_mixed_paed.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hx_rx_printed_gp.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hx_rx_printed_gp_photo.heic: detected=False unflagged_invented=4 false_alarm=False
- dev/invoice_pharmacy_gst.png: detected=True unflagged_invented=0 false_alarm=False
- dev/lab_report_degraded.png: detected=True unflagged_invented=0 false_alarm=False
- dev/lab_report_scan.png: detected=True unflagged_invented=0 false_alarm=False
- dev/mixed_printed_handwritten.png: detected=False unflagged_invented=4 false_alarm=False
- dev/pharma_info_minipress_letter.png: detected=True unflagged_invented=0 false_alarm=False
- dev/prescription_degraded.png: detected=True unflagged_invented=0 false_alarm=False
- dev/prescription_handwritten.png: detected=True unflagged_invented=0 false_alarm=False
- dev/prescription_photo_handheld.jpg: detected=False unflagged_invented=4 false_alarm=False
- dev/prescription_scan.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_nonmedical_notice.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_rx_hand_banerjee.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_rx_hand_iqbal.png: detected=False unflagged_invented=4 false_alarm=False
