import { createVerify } from "node:crypto";
import { readFileSync } from "node:fs";

const [publicKeyPath, filePath, signaturePath] = process.argv.slice(2);
if (!publicKeyPath || !filePath || !signaturePath) {
  console.error("usage: verify-release-signature.mjs <public-key> <file> <signature>");
  process.exit(2);
}

try {
  const verifier = createVerify("RSA-SHA256");
  verifier.update(readFileSync(filePath));
  verifier.end();
  const valid = verifier.verify(readFileSync(publicKeyPath), readFileSync(signaturePath));
  if (!valid) {
    console.error("release signature verification failed");
    process.exit(1);
  }
} catch (error) {
  console.error(`release signature verification unavailable: ${error.message}`);
  process.exit(1);
}
