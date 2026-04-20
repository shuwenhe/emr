package main

import (
    "bytes"
    "crypto/aes"
    "crypto/md5"
    "encoding/base64"
    "encoding/hex"
    "encoding/json"
    "errors"
    "io/ioutil"
    "net/http"
    "strings"
    "time"
)

// md5Upper16 returns the uppercase hex MD5 and takes the first 16 characters.
func md5Upper16(s string) string {
    h := md5.Sum([]byte(s))
    full := hex.EncodeToString(h[:])
    if len(full) >= 16 {
        return strings.ToUpper(full[:16])
    }
    return strings.ToUpper(full)
}

func pkcs7Pad(data []byte, blockSize int) []byte {
    pad := blockSize - len(data)%blockSize
    b := bytes.Repeat([]byte{byte(pad)}, pad)
    return append(data, b...)
}

func pkcs7Unpad(data []byte) ([]byte, error) {
    if len(data) == 0 {
        return nil, errors.New("invalid padding size")
    }
    pad := int(data[len(data)-1])
    if pad <= 0 || pad > len(data) {
        return nil, errors.New("invalid padding")
    }
    for i := len(data) - pad; i < len(data); i++ {
        if int(data[i]) != pad {
            return nil, errors.New("invalid padding bytes")
        }
    }
    return data[:len(data)-pad], nil
}

func aesEncryptECB(src, key []byte) ([]byte, error) {
    if len(key) != 16 && len(key) != 24 && len(key) != 32 {
        return nil, errors.New("invalid AES key size: must be 16/24/32 bytes")
    }
    block, err := aes.NewCipher(key)
    if err != nil {
        return nil, err
    }
    bs := block.BlockSize()
    src = pkcs7Pad(src, bs)
    dst := make([]byte, len(src))
    for i := 0; i < len(src); i += bs {
        block.Encrypt(dst[i:i+bs], src[i:i+bs])
    }
    return dst, nil
}

func aesDecryptECB(src, key []byte) ([]byte, error) {
    if len(key) != 16 && len(key) != 24 && len(key) != 32 {
        return nil, errors.New("invalid AES key size: must be 16/24/32 bytes")
    }
    block, err := aes.NewCipher(key)
    if err != nil {
        return nil, err
    }
    bs := block.BlockSize()
    if len(src)%bs != 0 {
        return nil, errors.New("ciphertext is not a multiple of block size")
    }
    dst := make([]byte, len(src))
    for i := 0; i < len(src); i += bs {
        block.Decrypt(dst[i:i+bs], src[i:i+bs])
    }
    return pkcs7Unpad(dst)
}

// EncryptJSONToBase64 encrypts the given value (marshalled as JSON) with AES-ECB PKCS7
// and returns a base64 string.
func EncryptJSONToBase64(v interface{}, keyStr string) (string, error) {
    b, err := json.Marshal(v)
    if err != nil {
        return "", err
    }
    enc, err := aesEncryptECB(b, []byte(keyStr))
    if err != nil {
        return "", err
    }
    return base64.StdEncoding.EncodeToString(enc), nil
}

func DecryptBase64ToJSON(b64, keyStr string) ([]byte, error) {
    raw, err := base64.StdEncoding.DecodeString(b64)
    if err != nil {
        return nil, err
    }
    dec, err := aesDecryptECB(raw, []byte(keyStr))
    if err != nil {
        return nil, err
    }
    return dec, nil
}

// PostEncrypted sends the encrypted payload in JSON as {"Data": "<base64>"}.
// If apiToken is non-empty it will be added as the `ApiToken` header.
func PostEncrypted(url, apiToken, keyStr string, payload interface{}) (int, []byte, error) {
    encoded, err := EncryptJSONToBase64(payload, keyStr)
    if err != nil {
        return 0, nil, err
    }
    bodyMap := map[string]string{"Data": encoded}
    bodyBytes, _ := json.Marshal(bodyMap)
    req, err := http.NewRequest("POST", url, bytes.NewReader(bodyBytes))
    if err != nil {
        return 0, nil, err
    }
    req.Header.Set("Content-Type", "application/json")
    if apiToken != "" {
        req.Header.Set("ApiToken", apiToken)
    }
    client := &http.Client{}
    resp, err := client.Do(req)
    if err != nil {
        return 0, nil, err
    }
    defer resp.Body.Close()
    respBody, _ := ioutil.ReadAll(resp.Body)
    return resp.StatusCode, respBody, nil
}

// APIClient manages server, account, key and ApiToken.
type APIClient struct {
    Server     string
    Account    string
    Key        string
    ApiToken   string
    HTTPClient *http.Client
}

func NewAPIClient(server, account string) *APIClient {
    return &APIClient{
        Server:   strings.TrimRight(server, "/"),
        Account:  account,
        Key:      MakeKey(account),
        HTTPClient: &http.Client{Timeout: 15 * time.Second},
    }
}

// DoPlainRequest sends a plain JSON POST (used for login).
func (c *APIClient) DoPlainRequest(path string, payload interface{}) (int, []byte, error) {
    url := c.Server + path
    b, err := json.Marshal(payload)
    if err != nil {
        return 0, nil, err
    }
    req, err := http.NewRequest("POST", url, bytes.NewReader(b))
    if err != nil {
        return 0, nil, err
    }
    req.Header.Set("Content-Type", "application/json")
    resp, err := c.HTTPClient.Do(req)
    if err != nil {
        return 0, nil, err
    }
    defer resp.Body.Close()
    rb, _ := ioutil.ReadAll(resp.Body)
    return resp.StatusCode, rb, nil
}

// DoEncryptedRequest sends encrypted payload and attempts to decrypt response Data if present.
func (c *APIClient) DoEncryptedRequest(path string, payload interface{}) (int, []byte, error) {
    url := c.Server + path
    encoded, err := EncryptJSONToBase64(payload, c.Key)
    if err != nil {
        return 0, nil, err
    }
    bodyMap := map[string]string{"Data": encoded}
    bodyBytes, _ := json.Marshal(bodyMap)
    req, err := http.NewRequest("POST", url, bytes.NewReader(bodyBytes))
    if err != nil {
        return 0, nil, err
    }
    req.Header.Set("Content-Type", "application/json")
    if c.ApiToken != "" {
        req.Header.Set("ApiToken", c.ApiToken)
    }
    resp, err := c.HTTPClient.Do(req)
    if err != nil {
        return 0, nil, err
    }
    defer resp.Body.Close()
    rb, _ := ioutil.ReadAll(resp.Body)

    // Try to parse JSON and if `Data` is present as string, decrypt it.
    var top map[string]interface{}
    if err := json.Unmarshal(rb, &top); err == nil {
        // Try both capitalized "Data" and lowercase "data" keys.
        if dataRaw, ok := top["Data"]; ok {
            if s, ok := dataRaw.(string); ok && s != "" {
                dec, derr := DecryptBase64ToJSON(s, c.Key)
                if derr == nil {
                    // attempt to extract token from decrypted JSON
                    var maybe map[string]interface{}
                    if json.Unmarshal(dec, &maybe) == nil {
                        if tok, ok := maybe["token"].(string); ok && tok != "" {
                            c.ApiToken = tok
                        }
                    }
                    return resp.StatusCode, dec, nil
                }
            }
        } else if dataRaw, ok := top["data"]; ok {
            switch v := dataRaw.(type) {
            case string:
                if v != "" {
                    dec, derr := DecryptBase64ToJSON(v, c.Key)
                    if derr == nil {
                        // attempt to extract token from decrypted JSON
                        var maybe map[string]interface{}
                        if json.Unmarshal(dec, &maybe) == nil {
                            if tok, ok := maybe["token"].(string); ok && tok != "" {
                                c.ApiToken = tok
                            }
                        }
                        return resp.StatusCode, dec, nil
                    }
                }
            case map[string]interface{}:
                // marshal object and return it
                if tok, ok := v["token"].(string); ok && tok != "" {
                    c.ApiToken = tok
                }
                if marsh, err := json.Marshal(v); err == nil {
                    return resp.StatusCode, marsh, nil
                }
            }
        }
        // also check top-level ApiToken
        if topToken, ok := top["ApiToken"]; ok {
            if t, ok := topToken.(string); ok && t != "" {
                c.ApiToken = t
            }
        }
    }

    return resp.StatusCode, rb, nil
}

// Helper to create the encryption key from account string as described in the document.
func KeyFromAccount(account string) string {
    return md5Upper16(account)
}

// Quick debug helper to pretty-print JSON responses (used by demo main)
func prettyJSON(b []byte) string {
    var out bytes.Buffer
    err := json.Indent(&out, b, "", "  ")
    if err != nil {
        return string(b)
    }
    return out.String()
}

// Exported for demo use in main.go
var (
    Encrypt = EncryptJSONToBase64
    PostEnc = PostEncrypted
    MakeKey = KeyFromAccount
    Pretty  = prettyJSON
)
