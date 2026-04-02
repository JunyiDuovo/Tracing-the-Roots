-- Bootstrap app_user + genealogy before COPY member (ASCII source; safe for Windows psql + GBK console).
-- Titles/surnames match project members.csv (gen-1 male per tree). For other CSV run ensure_genealogy_for_members_csv.py

INSERT INTO app_user (username, password_hash, email)
SELECT
    'csv_import',
    '$placeholder$ use_website_user_or_UPDATE_password_hash',
    NULL
WHERE NOT EXISTS (SELECT 1 FROM app_user);

DO $$
DECLARE
    uid INTEGER;
BEGIN
    SELECT id INTO uid FROM app_user ORDER BY id LIMIT 1;
    IF uid IS NULL THEN
        RAISE EXCEPTION 'app_user still empty (unexpected)';
    END IF;

    INSERT INTO genealogy (id, title, surname, revision_date, created_by) VALUES
        (1,  U&'\674E\7199\535A\652F\FF08\6811' || '1' || U&'\FF09',  U&'\674E', CURRENT_DATE, uid),
        (2,  U&'\738B\8D85\946B\652F\FF08\6811' || '2' || U&'\FF09',  U&'\738B', CURRENT_DATE, uid),
        (3,  U&'\5F20\8BDA\6D77\652F\FF08\6811' || '3' || U&'\FF09',  U&'\5F20', CURRENT_DATE, uid),
        (4,  U&'\5218\5F70\652F\FF08\6811' || '4' || U&'\FF09',       U&'\5218', CURRENT_DATE, uid),
        (5,  U&'\9648\9038\65ED\652F\FF08\6811' || '5' || U&'\FF09',  U&'\9648', CURRENT_DATE, uid),
        (6,  U&'\6768\677E\5B87\652F\FF08\6811' || '6' || U&'\FF09',  U&'\6768', CURRENT_DATE, uid),
        (7,  U&'\8D75\708E\653F\652F\FF08\6811' || '7' || U&'\FF09',  U&'\8D75', CURRENT_DATE, uid),
        (8,  U&'\9EC4\9633\652F\FF08\6811' || '8' || U&'\FF09',       U&'\9EC4', CURRENT_DATE, uid),
        (9,  U&'\5468\6CF0\652F\FF08\6811' || '9' || U&'\FF09',       U&'\5468', CURRENT_DATE, uid),
        (10, U&'\5434\7545\65FA\652F\FF08\6811' || '10' || U&'\FF09', U&'\5434', CURRENT_DATE, uid)
    ON CONFLICT (id) DO UPDATE SET
        title = EXCLUDED.title,
        surname = EXCLUDED.surname,
        revision_date = EXCLUDED.revision_date,
        created_by = EXCLUDED.created_by;

    PERFORM setval(
        pg_get_serial_sequence('genealogy', 'id'),
        (SELECT COALESCE(MAX(id), 1) FROM genealogy)
    );
END $$;
