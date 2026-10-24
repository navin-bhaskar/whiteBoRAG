// Copy to config.js (gitignored) and fill in:
//   apiUrl: terraform -chdir=aws/infra output -raw api_base_url
//   apiKey: terraform -chdir=aws/infra output -raw query_api_key
window.WHITEBORAG = {
  apiUrl: "https://xxxxxxxxxx.execute-api.ap-south-1.amazonaws.com/v1",
  apiKey: "paste-the-query-local-key-here",
};
