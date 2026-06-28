import { parseAllowedEmails } from "@pawrrtal/api/src/Modules/Authentication/Config"
import { assert, describe, it } from "vitest"

describe("Authentication.Config", () => {
  it("should parse the allowed emails config", () => {
    const result = parseAllowedEmails("test@example.com")
    assert.strictEqual(result.size, 1)
    assert.isTrue(result.has("test@example.com"))
  })

  it("should parse comma-separated values", () => {
    const result = parseAllowedEmails("test@example.com,test2@example.com")
    assert.strictEqual(result.size, 2)
    assert.isTrue(result.has("test@example.com"))
    assert.isTrue(result.has("test2@example.com"))
  })

  it("should parse empty string", () => {
    const result = parseAllowedEmails("")
    assert.strictEqual(result.size, 0)
  })

  it("should parse whitespace-separated values", () => {
    const result = parseAllowedEmails("test@example.com, test2@example.com")
    assert.strictEqual(result.size, 2)
    assert.isTrue(result.has("test@example.com"))
    assert.isTrue(result.has("test2@example.com"))
  })

  it("should parse case-insensitive values", () => {
    const result = parseAllowedEmails("test@example.com, Test2@example.com")
    assert.strictEqual(result.size, 2)
    assert.isTrue(result.has("test@example.com"))
    assert.isTrue(result.has("test2@example.com"))
  })

  it("should parse duplicate values", () => {
    const result = parseAllowedEmails("test@example.com, test@example.com")
    assert.strictEqual(result.size, 1)
    assert.isTrue(result.has("test@example.com"))
  })
})
