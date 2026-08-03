import { defineConfig } from "orval";

export default defineConfig({
  erp: {
    input: "../backend/openapi.json",
    output: {
      target: "src/lib/api/generated/endpoints.ts",
      schemas: "src/lib/api/generated/model",
      client: "react-query",
      httpClient: "axios",
      clean: true,
      override: {
        mutator: {
          path: "src/lib/api/axios.ts",
          name: "apiMutator",
        },
      },
    },
  },
});
