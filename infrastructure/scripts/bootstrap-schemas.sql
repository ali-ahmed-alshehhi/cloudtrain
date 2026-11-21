-- CloudTrain schema bootstrap (run once on a new RDS instance).
-- Mirrors local/postgres/init.sh: one LOGIN role + schema per service.
-- Owners: Hamda + Fatma.
--
-- Replace CHANGE_ME_* passwords before running (or use bootstrap-schemas.sh).
-- Connect as the RDS master user to database "cloudtrain".

CREATE ROLE projects  LOGIN PASSWORD 'CHANGE_ME_projects';
CREATE SCHEMA projects  AUTHORIZATION projects;

CREATE ROLE datasets  LOGIN PASSWORD 'CHANGE_ME_datasets';
CREATE SCHEMA datasets  AUTHORIZATION datasets;

CREATE ROLE jobs      LOGIN PASSWORD 'CHANGE_ME_jobs';
CREATE SCHEMA jobs      AUTHORIZATION jobs;

CREATE ROLE scheduler LOGIN PASSWORD 'CHANGE_ME_scheduler';
CREATE SCHEMA scheduler AUTHORIZATION scheduler;

CREATE ROLE registry  LOGIN PASSWORD 'CHANGE_ME_registry';
CREATE SCHEMA registry  AUTHORIZATION registry;

CREATE ROLE mlflow    LOGIN PASSWORD 'CHANGE_ME_mlflow';
CREATE SCHEMA mlflow    AUTHORIZATION mlflow;
