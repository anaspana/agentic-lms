# Dnevnik rada

Agentski LMS (SOTIS, Projekat 10) i njegov semantički sloj (Projekat 4).

## Nedelja 4 (26. 10. – 1. 11.)

Uradila sam pregled literature o agentima u LMS-u, MCP protokolu, agentnom upravljanju poslovnim procesima, process mining-u i evaluaciji agenata, i odredila gde se moje rešenje uklapa u postojeće radove. Profesoru sam poslala predlog pristupa i pitanja o modelu procesa, arhitekturi agenta i evaluaciji.

## Nedelja 5 (2. 11. – 8. 11.)

Na osnovu povratne informacije profesora definisala sam model procesa kao životni ciklus studenta na kursu: aktivnosti, preduslove, stanje izvedeno iz event loga i pravilo preporuke. Napravila sam backend (FastAPI) sa osam formi, bazom, event logom i preporukom sledeće akcije, uz test celog toka. Postavila sam GitHub repozitorijum.

## Nedelja 6 (9. 11. – 15. 11.)

Model procesa sam prebacila u deklarativni YAML fajl, iz kog backend čita preduslove i redosled preporuka, a agent će ga dobijati preko `GET /api/process`. Dodala sam proveru modela pri pokretanju i nove testove, a usput ispravila grešku zbog koje je nastavnik mogao da oceni zadatak sa drugog kursa. Dogovorila sam povezivanje projekta sa predmetom o semantičkom vebu.

## Nedelja 7 (16. 11. – 22. 11.)

Spojila sam granu sa deklarativnim modelom procesa u glavnu granu. Asistentu sam poslala predlog semantičkog sloja (ontologija procesa i događaja, standardi xAPI, Caliper i PROV-O, graf znanja dostupan agentu) i pitanja o obimu. Uvela sam ovaj dnevnik.