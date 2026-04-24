"""Wspolne fixtures + ustawianie minimalnych SELLER_* przed importem config.

Uzywamy przypisania `=`, nie `setdefault`, bo conftest MUSI wygrac z `.env`
uzytkownika — inaczej testy zachowuja sie roznie zaleznie od tego kto odpala
(np. SELLER_EMPLOYMENT_GROSS_ABOVE_MIN=true w prod .env zrobi fail
test_zus_dra::test_include_social_adds_social_tier, a MF_ENV=prod zrobi fail
test_jpk_submit_skill::test_dry_run_works_without_cert).
"""

import os

# Musi byc PRZED importem jdg_ksiegowy.config — pydantic-settings czyta env przy instancjacji.
os.environ["SELLER_NAME"] = "Test Sp. z o.o."
os.environ["SELLER_NIP"] = "1234567890"
os.environ["SELLER_ADDRESS"] = "ul. Testowa 1, 00-001 Warszawa"
os.environ["SELLER_BANK_ACCOUNT"] = "42 1140 0000 0000 0000 0000 0000"
os.environ["SELLER_BANK_NAME"] = "mBank"
os.environ["SELLER_FIRST_NAME"] = "Jan"
os.environ["SELLER_LAST_NAME"] = "Kowalski"
os.environ["SELLER_BIRTH_DATE"] = "1990-01-01"
os.environ["SELLER_TAX_OFFICE_CODE"] = "1471"
os.environ["SELLER_EMAIL"] = "test@example.com"
os.environ["MF_ENV"] = "test"
os.environ["MF_PESEL"] = ""
os.environ["MF_PRIOR_INCOME"] = "0"
# ZUS — ustaw deterministycznie, aby testy nie zalezaly od uzytkownika .env
os.environ["SELLER_BUSINESS_START_DATE"] = ""
os.environ["SELLER_ZUS_SOCIAL_MODE"] = "auto"
os.environ["SELLER_EMPLOYMENT_GROSS_ABOVE_MIN"] = "false"
os.environ["SELLER_ZUS_VOLUNTARY_SICKNESS"] = "false"
