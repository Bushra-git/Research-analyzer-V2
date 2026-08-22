-- Store a one-way password hash for optional authenticated accounts.
ALTER TABLE "User"
    ADD COLUMN "password_hash" TEXT;