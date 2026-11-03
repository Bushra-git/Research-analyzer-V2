FROM node:20-alpine

WORKDIR /app

# Prisma query engine needs OpenSSL compatibility on Alpine
RUN apk add --no-cache openssl

COPY package*.json ./
RUN npm ci


# Copy prisma schema + sources before generating Prisma client
COPY prisma ./prisma/
COPY . .

# Generate Prisma client during build so the container can start reliably
RUN npx prisma generate

EXPOSE 3001

CMD ["sh", "-c", "npx prisma migrate deploy && node server.js"]
