package main

import (
    "encoding/base64"
    "encoding/json"
    "net/http"
    "net/http/httptest"
    "strings"
    "testing"
)

func TestLoginAndAddCustomer(t *testing.T) {
    // create test server
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        switch r.URL.Path {
        case "/user/login":
            var lr LoginRequest
            _ = json.NewDecoder(r.Body).Decode(&lr)
            resp := map[string]interface{}{"code": 1, "data": map[string]string{"token": "test-token"}}
            _ = json.NewEncoder(w).Encode(resp)
            return
        case "/customer/add":
            // read encrypted payload
            var body map[string]string
            _ = json.NewDecoder(r.Body).Decode(&body)
            dataEnc := body["Data"]
            // decrypt using key derived from account header if present; for test we know account
            // In this test, client will use key derived from account "A2279".
            dec, derr := DecryptBase64ToJSON(dataEnc, MakeKey("A2279"))
            if derr != nil {
                http.Error(w, "bad decrypt", http.StatusBadRequest)
                return
            }
            // Check decrypted payload contains Mobile field
            var cust Customer
            _ = json.Unmarshal(dec, &cust)
            if strings.TrimSpace(cust.Mobile) == "" {
                http.Error(w, "missing mobile", http.StatusBadRequest)
                return
            }
            // Respond with encrypted data containing Id
            respData := map[string]string{"Id": "new-id-123"}
            respBytes, _ := json.Marshal(respData)
            encBytes, _ := aesEncryptECB(respBytes, []byte(MakeKey("A2279")))
            b64 := base64.StdEncoding.EncodeToString(encBytes)
            resp := map[string]interface{}{"code": 1, "data": b64}
            _ = json.NewEncoder(w).Encode(resp)
            return
        default:
            http.NotFound(w, r)
        }
    }))
    defer srv.Close()

    client := NewAPIClient(srv.URL, "A2279")

    // Test Login
    if err := client.Login("admin", "123456", "dev-1"); err != nil {
        t.Fatalf("login failed: %v", err)
    }
    if client.ApiToken != "test-token" {
        t.Fatalf("expected token 'test-token', got %q", client.ApiToken)
    }

    // Test AddCustomer
    c := Customer{RealName: "Alice", Mobile: "13800000000"}
    id, err := client.AddCustomer(c)
    if err != nil {
        t.Fatalf("AddCustomer failed: %v", err)
    }
    if id != "new-id-123" {
        t.Fatalf("unexpected id: %v", id)
    }
}

func TestReportAndImages(t *testing.T) {
    srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        switch r.URL.Path {
        case "/customer/SearchreportPageAndImagesV2":
            // return encrypted reports array
            reports := map[string]interface{}{"Reports": []map[string]interface{}{{"Id": 1001, "ProjectName": 2, "CName": "Alice", "Url": []string{"/r1"}}}}
            rb, _ := json.Marshal(reports)
            enc, _ := aesEncryptECB(rb, []byte(MakeKey("A2279")))
            b64 := base64.StdEncoding.EncodeToString(enc)
            _ = json.NewEncoder(w).Encode(map[string]interface{}{"code": 1, "data": b64})
            return
        case "/customer/AsyncchotimagesByReportId":
            var body map[string]string
            _ = json.NewDecoder(r.Body).Decode(&body)
            // decrypt incoming
            dec, derr := DecryptBase64ToJSON(body["Data"], MakeKey("A2279"))
            if derr != nil {
                http.Error(w, "bad decrypt", http.StatusBadRequest)
                return
            }
            var got map[string]string
            _ = json.Unmarshal(dec, &got)
            if got["Id"] == "1001" {
                arr := []map[string]string{{"ThermalImaging": "/img1", "ThermalDat": "/tmp1"}}
                rb, _ := json.Marshal(arr)
                enc, _ := aesEncryptECB(rb, []byte(MakeKey("A2279")))
                b64 := base64.StdEncoding.EncodeToString(enc)
                _ = json.NewEncoder(w).Encode(map[string]interface{}{"code": 1, "data": b64})
                return
            }
            http.Error(w, "not found", http.StatusNotFound)
        default:
            http.NotFound(w, r)
        }
    }))
    defer srv.Close()

    client := NewAPIClient(srv.URL, "A2279")

    // Get reports
    rb, err := client.GetReportsByClientId(123)
    if err != nil {
        t.Fatalf("GetReportsByClientId failed: %v", err)
    }
    // If DoEncryptedRequest did decrypt, rb will be decrypted JSON, otherwise try to decode envelope
    var reportsResp map[string]interface{}
    if err := json.Unmarshal(rb, &reportsResp); err != nil {
        t.Fatalf("invalid reports response: %v", err)
    }
    if reportsResp["Reports"] == nil {
        t.Fatalf("Reports missing in response")
    }

    // Get images for report 1001
    rb2, err := client.GetReportImages("1001")
    if err != nil {
        t.Fatalf("GetReportImages failed: %v", err)
    }
    var arr []map[string]string
    if err := json.Unmarshal(rb2, &arr); err != nil {
        t.Fatalf("invalid images response: %v", err)
    }
    if len(arr) == 0 || arr[0]["ThermalImaging"] == "" {
        t.Fatalf("unexpected images payload")
    }
}
