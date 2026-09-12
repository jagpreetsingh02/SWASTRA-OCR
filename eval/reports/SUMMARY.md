# Evaluation summary

Generated 2026-09-12 07:23 by `eval/run.py`.

## dev / text


Documents: 16 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.996 · recall 1.0 (tp 270, fp 1, fn 0)
False positives 1 · false negatives 0 · wrong values 0 · **unflagged errors 0** · placement errors 0 · grounding failures 0

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| allergies | 3 | 0 | 0 | 1.0 | 1.0 |
| date | 16 | 0 | 0 | 1.0 | 1.0 |
| diagnoses | 14 | 0 | 0 | 1.0 | 1.0 |
| doctor_name | 11 | 0 | 0 | 1.0 | 1.0 |
| medication | 41 | 0 | 0 | 1.0 | 1.0 |
| medication.dosage | 38 | 0 | 0 | 1.0 | 1.0 |
| medication.duration | 19 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 41 | 0 | 0 | 1.0 | 1.0 |
| patient_name | 7 | 0 | 0 | 1.0 | 1.0 |
| symptoms | 9 | 0 | 0 | 1.0 | 1.0 |
| test_result | 17 | 0 | 0 | 1.0 | 1.0 |
| test_result.reference_range | 13 | 0 | 0 | 1.0 | 1.0 |
| test_result.unit | 16 | 0 | 0 | 1.0 | 1.0 |
| test_result.value | 17 | 0 | 0 | 1.0 | 1.0 |
| tests | 8 | 1 | 0 | 0.889 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| discharge.txt | ok | 9/0/0 | 0 |  |  | — |
| discharge_copd.txt | ok | 19/0/0 | 0 |  |  | — |
| hw_rx_bradley.txt | ok | 18/0/0 | 0 |  |  | — |
| hw_rx_brush_hard.txt | ok | 11/0/0 | 0 |  |  | — |
| hw_rx_chalkboard.txt | ok | 14/0/0 | 0 |  |  | — |
| hw_rx_cursive.txt | ok | 15/0/0 | 0 |  |  | — |
| lab_haematology_table.txt | ok | 26/0/0 | 0 |  |  | — |
| lab_report.txt | ok | 29/0/0 | 0 |  |  | — |
| mixed_printed_handwritten.txt | ok | 15/0/0 | 0 |  |  | — |
| nonmedical_invoice.txt | ok | 1/0/0 | 0 |  |  | — |
| prescription.txt | ok | 21/0/0 | 0 |  |  | — |
| prescription_handwritten.txt | ok | 15/0/0 | 0 |  |  | — |
| probe_false_positives.txt | ok | 15/1/0 | 0 |  |  | false_positive tests: expected None got 'SpO2' (flagged) |
| probe_medication_formats.txt | ok | 24/0/0 | 0 |  |  | — |
| rx_clinic_uti.txt | ok | 22/0/0 | 0 |  |  | — |
| rx_paediatric_opd.txt | ok | 16/0/0 | 0 |  |  | — |

## dev / ocr


Documents: 16 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.978 · recall 0.978 (tp 271, fp 6, fn 6)
False positives 5 · false negatives 5 · wrong values 1 · **unflagged errors 0** · placement errors 0 · grounding failures 0

OCR critical tokens: accuracy 0.982 (date 15/16 · dosage 38/38 · duration 26/26 · frequency 40/40 · header 12/12 · lab_name 20/22 · lab_value 25/25 · medicine_name 39/40)
OCR mean CER 0.0051 · unsupported (invented/garbled) lines 0 · mean 9.06 s/file
Output distinctness (closest to its own source): 16/16

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| allergies | 1 | 0 | 0 | 1.0 | 1.0 |
| date | 15 | 1 | 1 | 0.938 | 0.938 |
| diagnoses | 14 | 2 | 2 | 0.875 | 0.875 |
| doctor_name | 10 | 0 | 0 | 1.0 | 1.0 |
| medication | 39 | 1 | 1 | 0.975 | 0.975 |
| medication.dosage | 37 | 0 | 0 | 1.0 | 1.0 |
| medication.duration | 25 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 39 | 0 | 0 | 1.0 | 1.0 |
| patient_name | 2 | 0 | 0 | 1.0 | 1.0 |
| symptoms | 5 | 0 | 0 | 1.0 | 1.0 |
| test_result | 20 | 2 | 2 | 0.909 | 0.909 |
| test_result.reference_range | 19 | 0 | 0 | 1.0 | 1.0 |
| test_result.unit | 19 | 0 | 0 | 1.0 | 1.0 |
| test_result.value | 20 | 0 | 0 | 1.0 | 1.0 |
| tests | 6 | 0 | 0 | 1.0 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| discharge.pdf | ok | 9/0/0 | 0 | 8/8 | 0.0 | — |
| discharge_degraded.png | ok | 9/0/0 | 0 | 8/8 | 0.0 | — |
| discharge_scan.png | ok | 9/0/0 | 0 | 8/8 | 0.0 | — |
| hw_rx_bradley.png | low_confidence | 18/0/0 | 0 | 14/14 | 0.0 | OCR read 'Rx' as 'RX' |
| hw_rx_brush_hard.png | ok | 10/1/1 | 0 | 9/10 | 0.031 | wrong_value date: expected '30/05/2026' got '30|05|2026' (flagged)<br>OCR missed date '30/05/2026'<br>OCR read '30/05/2026' as '30|05|2026'<br>OCR read '50mcg' as '50 mcg' |
| hw_rx_chalkboard.png | ok | 14/0/0 | 0 | 12/12 | 0.0 | — |
| hw_rx_cursive.png | ok | 13/2/2 | 0 | 11/11 | 0.031 | missing diagnoses: expected 'T2DM' got None<br>missing diagnoses: expected 'HTN' got None<br>false_positive diagnoses: expected None got 'T2D' (flagged)<br>false_positive diagnoses: expected None got 'H T N' (flagged)<br>OCR read 'T2DM, HTN' as 'T2D.M, H T N'<br>OCR read 'Adv:' as 'Ado:' |
| lab_report.pdf | ok | 29/0/0 | 0 | 16/16 | 0.0 | — |
| lab_report_degraded.png | ok | 25/1/1 | 0 | 15/16 | 0.003 | missing test_result: expected 'HbA1c' got None<br>false_positive test_result: expected None got 'HbAlc' (flagged)<br>OCR missed lab_name 'HbA1c'<br>OCR read 'HbA1c' as 'HbAlc' |
| lab_report_scan.png | ok | 25/1/1 | 0 | 15/16 | 0.003 | missing test_result: expected 'HbA1c' got None<br>false_positive test_result: expected None got 'HbAlc' (flagged)<br>OCR missed lab_name 'HbA1c'<br>OCR read 'HbA1c' as 'HbAlc' |
| mixed_printed_handwritten.png | ok | 15/0/0 | 0 | 13/13 | 0.0 | — |
| prescription.pdf | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |
| prescription_degraded.png | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |
| prescription_handwritten.png | ok | 11/1/1 | 0 | 14/15 | 0.013 | missing medication: expected 'Augmtin' got None<br>false_positive medication: expected None got 'Augmentin' (flagged)<br>OCR missed medicine_name 'Augmtin'<br>OCR read 'Rx' as 'RX'<br>OCR read 'Augmtin' as 'Augmentin' |
| prescription_photo_handheld.jpg | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |
| prescription_scan.png | ok | 21/0/0 | 0 | 18/18 | 0.0 | — |

## heldout / text


Documents: 9 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.956 · recall 0.901 (tp 172, fp 8, fn 19)
False positives 6 · false negatives 17 · wrong values 2 · **unflagged errors 7** · placement errors 0 · grounding failures 0

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| allergies | 1 | 2 | 0 | 0.333 | 1.0 |
| date | 8 | 1 | 1 | 0.889 | 0.889 |
| diagnoses | 7 | 0 | 0 | 1.0 | 1.0 |
| doctor_name | 7 | 0 | 0 | 1.0 | 1.0 |
| medication | 17 | 0 | 0 | 1.0 | 1.0 |
| medication.dosage | 14 | 1 | 1 | 0.933 | 0.933 |
| medication.duration | 7 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 16 | 0 | 1 | 1.0 | 0.941 |
| patient_name | 8 | 0 | 0 | 1.0 | 1.0 |
| symptoms | 6 | 0 | 0 | 1.0 | 1.0 |
| test_result | 24 | 0 | 0 | 1.0 | 1.0 |
| test_result.reference_range | 10 | 0 | 14 | 1.0 | 0.417 |
| test_result.unit | 22 | 0 | 2 | 1.0 | 0.917 |
| test_result.value | 24 | 0 | 0 | 1.0 | 1.0 |
| tests | 1 | 4 | 0 | 0.2 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| hx_discharge_kmc.txt | ok | 19/1/0 | 1 |  |  | false_positive tests: expected None got 'chest X-ray' (**NOT flagged**) |
| hx_lab_biochem.txt | ok | 20/1/6 | 1 |  |  | missing test_result.reference_range: expected '0.2 - 1.2' got None<br>missing test_result.reference_range: expected '7 - 56' got None<br>missing test_result.reference_range: expected '0.7 - 1.3' got None<br>missing test_result.reference_range: expected '15 - 40' got None<br>missing test_result.reference_range: expected '4.0 - 5.6' got None<br>missing test_result.reference_range: expected '3.5 - 5.1' got None<br>false_positive tests: expected None got 'ALT' (**NOT flagged**) |
| hx_lab_cbc.txt | ok | 25/1/2 | 1 |  |  | missing test_result.unit: expected 'mill/cumm' got None<br>missing test_result.reference_range: expected '3.8 - 4.8' got None<br>false_positive tests: expected None got 'COMPLETE BLOOD COUNT' (**NOT flagged**) |
| hx_labs_2page.txt | ok | 42/2/9 | 2 |  |  | wrong_value date: expected '09/08/2026' got '21-08-2026' (**NOT flagged**)<br>missing test_result.unit: expected 'mill/cumm' got None<br>missing test_result.reference_range: expected '3.8 - 4.8' got None<br>missing test_result.reference_range: expected '0.2 - 1.2' got None<br>missing test_result.reference_range: expected '7 - 56' got None<br>missing test_result.reference_range: expected '0.7 - 1.3' got None<br>missing test_result.reference_range: expected '15 - 40' got None<br>missing test_result.reference_range: expected '4.0 - 5.6' got None<br>missing test_result.reference_range: expected '3.5 - 5.1' got None<br>false_positive tests: expected None got 'ALT' (**NOT flagged**) |
| hx_mixed_paed.txt | ok | 18/0/0 | 0 |  |  | — |
| hx_nonmedical_notice.txt | ok | 1/0/0 | 0 |  |  | — |
| hx_rx_hand_banerjee.txt | ok | 14/1/2 | 1 |  |  | missing medication.frequency: expected 'BBF' got None<br>wrong_value medication.dosage: expected '2 tsp' got '2' (**NOT flagged**) |
| hx_rx_hand_iqbal.txt | ok | 14/0/0 | 0 |  |  | — |
| hx_rx_printed_gp.txt | ok | 19/2/0 | 1 |  |  | false_positive allergies: expected None got 'Allergies' (**NOT flagged**)<br>false_positive allergies: expected None got 'None known' (flagged) |

## heldout / ocr


Documents: 11 · crashes: 0 · document-type accuracy: 1.0
Extraction overall: precision 0.947 · recall 0.907 (tp 215, fp 12, fn 22)
False positives 9 · false negatives 19 · wrong values 3 · **unflagged errors 8** · placement errors 0 · grounding failures 0

OCR critical tokens: accuracy 1.0 (date 11/11 · dosage 19/19 · duration 9/9 · frequency 20/20 · header 21/21 · lab_name 30/30 · lab_value 32/32 · medicine_name 20/20)
OCR mean CER 0.0195 · unsupported (invented/garbled) lines 0 · mean 12.93 s/file
Output distinctness (closest to its own source): 11/11

| field | tp | fp | fn | precision | recall |
|---|---|---|---|---|---|
| allergies | 1 | 4 | 0 | 0.2 | 1.0 |
| date | 10 | 1 | 1 | 0.909 | 0.909 |
| diagnoses | 9 | 0 | 0 | 1.0 | 1.0 |
| doctor_name | 9 | 0 | 0 | 1.0 | 1.0 |
| medication | 20 | 0 | 0 | 1.0 | 1.0 |
| medication.dosage | 17 | 1 | 1 | 0.944 | 0.944 |
| medication.duration | 9 | 0 | 0 | 1.0 | 1.0 |
| medication.frequency | 19 | 0 | 1 | 1.0 | 0.95 |
| patient_name | 9 | 1 | 1 | 0.9 | 0.9 |
| symptoms | 8 | 0 | 0 | 1.0 | 1.0 |
| test_result | 30 | 0 | 0 | 1.0 | 1.0 |
| test_result.reference_range | 15 | 0 | 15 | 1.0 | 0.5 |
| test_result.unit | 27 | 0 | 3 | 1.0 | 0.9 |
| test_result.value | 30 | 0 | 0 | 1.0 | 1.0 |
| tests | 2 | 5 | 0 | 0.286 | 1.0 |

| document | status | tp/fp/fn | unflagged | critical tokens | CER | problems |
|---|---|---|---|---|---|---|
| hx_discharge_kmc.png | ok | 18/2/1 | 2 | 16/16 | 0.0 | wrong_value patient_name: expected 'Lakshmi Iyer' got 'Lakshmi Iyer IP' (**NOT flagged**)<br>false_positive tests: expected None got 'chest X-ray' (**NOT flagged**) |
| hx_lab_biochem.png | ok | 20/1/6 | 1 | 15/15 | 0.0 | missing test_result.reference_range: expected '0.2 - 1.2' got None<br>missing test_result.reference_range: expected '7 - 56' got None<br>missing test_result.reference_range: expected '0.7 - 1.3' got None<br>missing test_result.reference_range: expected '15 - 40' got None<br>missing test_result.reference_range: expected '4.0 - 5.6' got None<br>missing test_result.reference_range: expected '3.5 - 5.1' got None<br>false_positive tests: expected None got 'ALT' (**NOT flagged**) |
| hx_lab_cbc.png | low_confidence | 25/1/2 | 0 | 15/15 | 0.084 | missing test_result.unit: expected 'mill/cumm' got None<br>missing test_result.reference_range: expected '3.8 - 4.8' got None<br>false_positive tests: expected None got 'COMPLETE BLOOD COUNT' (flagged) |
| hx_lab_cbc_degraded.jpg | low_confidence | 25/1/2 | 0 | 15/15 | 0.084 | missing test_result.unit: expected 'mill/cumm' got None<br>missing test_result.reference_range: expected '3.8 - 4.8' got None<br>false_positive tests: expected None got 'COMPLETE BLOOD COUNT' (flagged) |
| hx_labs_2page.pdf | low_confidence | 42/2/9 | 2 | 28/28 | 0.046 | wrong_value date: expected '09/08/2026' got '21-08-2026' (**NOT flagged**)<br>missing test_result.unit: expected 'mill/cumm' got None<br>missing test_result.reference_range: expected '3.8 - 4.8' got None<br>missing test_result.reference_range: expected '0.2 - 1.2' got None<br>missing test_result.reference_range: expected '7 - 56' got None<br>missing test_result.reference_range: expected '0.7 - 1.3' got None<br>missing test_result.reference_range: expected '15 - 40' got None<br>missing test_result.reference_range: expected '4.0 - 5.6' got None<br>missing test_result.reference_range: expected '3.5 - 5.1' got None<br>false_positive tests: expected None got 'ALT' (**NOT flagged**) |
| hx_mixed_paed.png | ok | 18/0/0 | 0 | 15/15 | 0.0 | — |
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

Hallucination detector (OCR stubbed with the true text plus one invented line): detected **19/23**, invented-line entities not flagged **16**, false alarms on clean text 0/23

- dev/discharge_degraded.png: detected=True unflagged_invented=0 false_alarm=False
- dev/discharge_scan.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hw_rx_bradley.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hw_rx_brush_hard.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hw_rx_chalkboard.png: detected=True unflagged_invented=0 false_alarm=False
- dev/hw_rx_cursive.png: detected=True unflagged_invented=0 false_alarm=False
- dev/lab_report_degraded.png: detected=True unflagged_invented=0 false_alarm=False
- dev/lab_report_scan.png: detected=True unflagged_invented=0 false_alarm=False
- dev/mixed_printed_handwritten.png: detected=False unflagged_invented=4 false_alarm=False
- dev/prescription_degraded.png: detected=True unflagged_invented=0 false_alarm=False
- dev/prescription_handwritten.png: detected=True unflagged_invented=0 false_alarm=False
- dev/prescription_photo_handheld.jpg: detected=False unflagged_invented=4 false_alarm=False
- dev/prescription_scan.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_discharge_kmc.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_lab_biochem.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_lab_cbc.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_lab_cbc_degraded.jpg: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_mixed_paed.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_nonmedical_notice.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_rx_hand_banerjee.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_rx_hand_iqbal.png: detected=False unflagged_invented=4 false_alarm=False
- heldout/hx_rx_printed_gp.png: detected=True unflagged_invented=0 false_alarm=False
- heldout/hx_rx_printed_gp_photo.heic: detected=False unflagged_invented=4 false_alarm=False
