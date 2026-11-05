# Example citations per verdict

## verified-correct

- **gpt-4o / Q15** · raw `(1999) 1 Sri L.R. 157` · name `Karunathilaka v. Dayananda Dissanayake, Commissioner of Elections and Others` · principle: *Dayananda Dissanayake, Commissioner of Elections and Others (1999) 1 Sri L.R. 157**: The Supreme Court reiterated that d* · reason: report_key match + name match (Karunathilaka and Another vs. Dayananda Dissanayake, and Com)
- **gpt-4o / Q15** · raw `(2000) 3 Sri L.R. 243` · name `Bulankulama and Others v. Secretary, Ministry of Industrial Development and Others` · principle: *Secretary, Ministry of Industrial Development and Others (2000) 3 Sri L.R. 243**: This case involved a challenge to a Ca* · reason: report_key match + name match (Bulankulama v. Secretary, Ministry of Industrial Development)

## exists-name-unverified

- **gpt-4o-mini / Q30** · raw `(2001) 1 Sri LR 1` · name `-` · principle: *Perera** (2001) 1 Sri LR 1, the court discussed the importance of causa, stating that a contract without a lawful causa * · reason: report_key SLR_2001_1_1 exists in graph; DB has no stored name to verify
- **gpt-4o-mini / Q55** · raw `[2001] 1 Sri LR 1` · name `-` · principle: *The Attorney General* [2001] 1 Sri LR 1. - **Principle**: The court emphasized that the right to bail is a fundamental r* · reason: report_key SLR_2001_1_1 exists in graph; DB has no stored name to verify

## number-exists-unverified

- **gpt-4o-mini / Q04** · raw `[2000] 1 Sri LR 1` · name `-` · principle: ***Citation:** [2000] 1 Sri LR 1 **Year:** 2000 **Principle:** The Supreme Court ruled that an arrest made solely on the * · reason: citation SLR_2000_1_1 exists in external index (M. A. Razak &Co. Ltd. v. Lanka Walltiles Ltd.); AI g
- **gpt-4o-mini / Q05** · raw `[2000] 1 Sri LR 1` · name `-` · principle: *Citation: [2000] 1 Sri LR 1 Year: 2000 Principle: In this case, the Supreme Court held that the police had subjected the* · reason: citation SLR_2000_1_1 exists in external index (M. A. Razak &Co. Ltd. v. Lanka Walltiles Ltd.); AI g

## name-mismatch

- **gpt-4o / Q30** · raw `(1925) 27 NLR 33` · name `Perera v. Perera_` · principle: *Perera_ (1925) 27 NLR 33**: This case discusses the concept of causa* · reason: report_key NLR_27_33 in DB as DIFFERENT case (model: Perera v. Perera_ | DB: Hameedu Lebbe v. Ganith
- **gpt-4o / Q34** · raw `(1958) 60 NLR 457` · name `Sinnathamby v. Kanagasabai` · principle: *Kanagasabai (1958) 60 NLR 457** - This case involved a lease agreement that was frustrated due to the requisitioning of * · reason: report_key NLR_60_457 in DB as DIFFERENT case (model: Sinnathamby v. Kanagasabai | DB: Wijewardena v

## wrong-case

- **gpt-4o / Q47** · raw `(1926) 28 NLR 225` · name `King v. Assappu` · principle: *Assappu (1926) 28 NLR 225**: In this case, the Supreme Court of Ceylon (as Sri Lanka was then known) held that for commo* · reason: citation NLR_28_225 exists externally as DIFFERENT case (Ukku Rala Korale v. Punchi Appuhamy; AI sai
- **gpt-4o / Q70** · raw `[1992] 1 Sri LR 1` · name `Fernando v. The Ceylon Petroleum Corporation` · principle: *The Ceylon Petroleum Corporation [1992] 1 Sri LR 1**: - **Year**: 1992 - **Principle**: The Supreme Court reiterated tha* · reason: citation SLR_1992_1_1 exists externally as DIFFERENT case (Abeysekera v. Carolis; AI said Fernando v

## real-name-wrong-citation

- **gpt-4o / Q15** · raw `(2001) 1 Sri L.R. 33` · name `Ekanayake v. Attorney General` · principle: *Attorney General (2001) 1 Sri L.R. 33**: In this case, the Supreme Court held that executive actions, including those of* · reason: name matches an external case (Ekanayake (R.P.C 9503) v. Reserve Sub Inspector, Hewawasam a) but cit
- **gpt-4o / Q16** · raw `(2003) 1 SLR 157` · name `Karunathilaka and Another v. Dayananda Dissanayake, Commissioner of Elections and Others` · principle: *Dayananda Dissanayake, Commissioner of Elections and Others (2003) 1 SLR 157** - In this case, the Supreme Court dealt w* · reason: name matches an external case (Gamini Atukorale v. Dayananda Dissanayake, Commissioner of E) but cit

## not-found-anywhere

- **gpt-4o-mini / Q04** · raw `SC Appeal No. 12/2001` · name `-` · principle: ***Citation:** SC Appeal No. 12/2001,* · reason: cited year 2001 is before our corpus (2009-2025) and not in external index
- **gpt-4o-mini / Q05** · raw `SC (FR) Application No. 192/2001` · name `-` · principle: *Citation: SC (FR) Application No. 192/2001 Year: 2003 Principle: The Supreme Court found that the petitioner had been su* · reason: cited year 2001 is before our corpus (2009-2025) and not in external index

## unverifiable

- **gpt-4o-mini / Q16** · raw `SC Appeal No. 1/2018` · name `-` · principle: *Citation: SC Appeal No. 1/2018 Year: 2018 Principle: This case involved the interpretation of the President's powers con* · reason: cited year 2018 is after lankalaw index (2011); cannot verify
- **gpt-4o-mini / Q16** · raw `SC FR Application No. 220/2018` · name `-` · principle: *Citation: SC FR Application No. 220/2018 Year: 2019 Principle: In this case, the Supreme Court examined the legality of * · reason: cited year 2018 is after lankalaw index (2011); cannot verify

## undecidable

- **gpt-4o-mini / Q04** · raw `[1999] 1 Sri LR 1` · name `-` · principle: ***Citation:** [1999] 1 Sri LR 1 **Year:** 1999 **Principle:** In this case, the Supreme Court held that an arrest made w* · reason: report_key exists; model gave no case name (DB: Cooray v Bandaranayake)
- **gpt-4o-mini / Q07** · raw `[1998] 1 Sri LR 1` · name `-` · principle: *Citation: [1998] 1 Sri LR 1 Year: 1998 Principle: In this case, the Supreme Court recognized that the family members of * · reason: report_key exists; model gave no case name (DB: Bhojraj v. Abdulla)

