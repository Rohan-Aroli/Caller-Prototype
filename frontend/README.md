# Frontend Development Setup

This project uses Vite + React + TypeScript to provide a simple web interface for uploading CSV leads.

## Prerequisites

- Node.js >= 18
- npm

## Setup

First, ensure the frontend environment variables are configured:
```bash
cp .env.example .env
```
(Modify `VITE_API_BASE_URL` in `.env` if your backend is running on a different port/host).

## Running the Frontend

To install dependencies and start the development server:
```bash
npm install
npm run dev --host
```

The app will typically be available at `http://localhost:5173`.
