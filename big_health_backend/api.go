package main

import (
    "bytes"
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "io/ioutil"
    "mime/multipart"
    "net/http"
    "os"
    "path/filepath"
)

// Login performs plain login (not encrypted) and stores ApiToken on success.
func (c *APIClient) Login(username, password, deviceSn string) error {
    req := LoginRequest{Username: username, Password: password, DeviceSn: deviceSn}
    status, rb, err := c.DoPlainRequest("/user/login", req)
    if err != nil {
        return err
    }
    if status < 200 || status >= 300 {
        return fmt.Errorf("login HTTP status %d", status)
    }
    var env ResponseEnvelope
    if err := json.Unmarshal(rb, &env); err != nil {
        return err
    }
    if env.Code != 1 {
        return fmt.Errorf("login failed: %s", env.ErrMsg)
    }
    // Data may be object containing token
    var raw map[string]interface{}
    if len(env.Data) > 0 {
        _ = json.Unmarshal(env.Data, &raw)
    }
    if raw != nil {
        if t, ok := raw["token"].(string); ok && t != "" {
            c.ApiToken = t
            return nil
        }
        if t, ok := raw["ApiToken"].(string); ok && t != "" {
            c.ApiToken = t
            return nil
        }
    }
    return errors.New("login succeeded but token not found in response")
}

// Logout calls the logout endpoint (plain or encrypted per doc; doc shows plain suffix /user/LoginOff).
func (c *APIClient) Logout() error {
    status, rb, err := c.DoPlainRequest("/user/LoginOff", map[string]string{})
    if err != nil {
        return err
    }
    if status < 200 || status >= 300 {
        return fmt.Errorf("logout HTTP status %d: %s", status, string(rb))
    }
    c.ApiToken = ""
    return nil
}

// AddCustomer adds a new customer (encrypted request per doc)
func (c *APIClient) AddCustomer(customer Customer) (string, error) {
    status, rb, err := c.DoEncryptedRequest("/customer/add", customer)
    if err != nil {
        return "", err
    }
    if status < 200 || status >= 300 {
        return "", fmt.Errorf("add customer HTTP status %d: %s", status, string(rb))
    }
    // Try to parse as full envelope first
    var env ResponseEnvelope
    if err := json.Unmarshal(rb, &env); err == nil && env.Code != 0 {
        if env.Code != 1 {
            return "", fmt.Errorf("add customer failed: %s", env.ErrMsg)
        }
        // env.Data may be an object or encrypted string depending on server; try to parse Id
        var data map[string]interface{}
        if len(env.Data) > 0 {
            _ = json.Unmarshal(env.Data, &data)
            if idv, ok := data["Id"].(string); ok {
                return idv, nil
            }
            if idv, ok := data["Orderid"].(string); ok {
                return idv, nil
            }
        }
        return "", nil
    }

    // Otherwise, try to parse rb as data-only JSON (e.g., {"Id":"..."})
    var data map[string]interface{}
    if err := json.Unmarshal(rb, &data); err == nil {
        if idv, ok := data["Id"].(string); ok {
            return idv, nil
        }
        if idv, ok := data["Orderid"].(string); ok {
            return idv, nil
        }
    }
    return "", nil
}

// UpdateCustomer updates a customer (encrypted)
func (c *APIClient) UpdateCustomer(customer Customer) error {
    status, rb, err := c.DoEncryptedRequest("/customer/updata", customer)
    if err != nil {
        return err
    }
    if status < 200 || status >= 300 {
        return fmt.Errorf("update customer HTTP status %d: %s", status, string(rb))
    }
    var env ResponseEnvelope
    if err := json.Unmarshal(rb, &env); err != nil {
        return err
    }
    if env.Code != 1 {
        return fmt.Errorf("update customer failed: %s", env.ErrMsg)
    }
    return nil
}

// SearchCustomers performs /customer/SearchbyuserPage
func (c *APIClient) SearchCustomers(req SearchCustomersRequest) (*SearchCustomersResponse, error) {
    status, rb, err := c.DoEncryptedRequest("/customer/SearchbyuserPage", req)
    if err != nil {
        return nil, err
    }
    if status < 200 || status >= 300 {
        return nil, fmt.Errorf("search customers HTTP status %d: %s", status, string(rb))
    }
    var resp SearchCustomersResponse
    if err := json.Unmarshal(rb, &resp); err != nil {
        return nil, err
    }
    return &resp, nil
}

// SaveReportV2 uploads multipart/form-data report (doc says multipart/form-data and not encrypted)
func (c *APIClient) SaveReportV2(fields map[string]string, imagePaths []string) ([]byte, error) {
    // build multipart body
    var b bytes.Buffer
    w := multipart.NewWriter(&b)
    for k, v := range fields {
        _ = w.WriteField(k, v)
    }
    for _, p := range imagePaths {
        f, err := os.Open(p)
        if err != nil {
            return nil, err
        }
        defer f.Close()
        part, err := w.CreateFormFile("files", filepath.Base(p))
        if err != nil {
            return nil, err
        }
        if _, err := ioCopy(part, f); err != nil {
            return nil, err
        }
    }
    w.Close()

    url := c.Server + "/customer/SaveReportV2"
    req, err := http.NewRequest("POST", url, &b)
    if err != nil {
        return nil, err
    }
    req.Header.Set("Content-Type", w.FormDataContentType())
    if c.ApiToken != "" {
        req.Header.Set("ApiToken", c.ApiToken)
    }
    resp, err := c.HTTPClient.Do(req)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    rb, _ := ioutil.ReadAll(resp.Body)
    if resp.StatusCode < 200 || resp.StatusCode >= 300 {
        return rb, fmt.Errorf("SaveReportV2 HTTP status %d", resp.StatusCode)
    }
    return rb, nil
}

// GetCurrentUser fetches current user info
func (c *APIClient) GetCurrentUser() ([]byte, error) {
    status, rb, err := c.DoEncryptedRequest("/user/search", map[string]string{})
    if err != nil {
        return nil, err
    }
    if status < 200 || status >= 300 {
        return nil, fmt.Errorf("get current user HTTP status %d: %s", status, string(rb))
    }
    return rb, nil
}

// UpdateUser updates current user info
func (c *APIClient) UpdateUser(user interface{}) error {
    status, rb, err := c.DoEncryptedRequest("/user/updata", user)
    if err != nil {
        return err
    }
    if status < 200 || status >= 300 {
        return fmt.Errorf("update user HTTP status %d: %s", status, string(rb))
    }
    var env ResponseEnvelope
    if err := json.Unmarshal(rb, &env); err != nil {
        return err
    }
    if env.Code != 1 {
        return fmt.Errorf("update user failed: %s", env.ErrMsg)
    }
    return nil
}

// UpdatePassword updates user password
func (c *APIClient) UpdatePassword(oldPwd, newPwd string) error {
    req := map[string]string{"Password": oldPwd, "NewPassword": newPwd}
    status, rb, err := c.DoEncryptedRequest("/user/updatepwd", req)
    if err != nil {
        return err
    }
    if status < 200 || status >= 300 {
        return fmt.Errorf("update password HTTP status %d: %s", status, string(rb))
    }
    var env ResponseEnvelope
    if err := json.Unmarshal(rb, &env); err != nil {
        return err
    }
    if env.Code != 1 {
        return fmt.Errorf("update password failed: %s", env.ErrMsg)
    }
    return nil
}

// DeleteCustomer deletes a customer by id
func (c *APIClient) DeleteCustomer(customerId string) error {
    req := map[string]string{"CustomerId": customerId}
    status, rb, err := c.DoEncryptedRequest("/customer/delete", req)
    if err != nil {
        return err
    }
    if status < 200 || status >= 300 {
        return fmt.Errorf("delete customer HTTP status %d: %s", status, string(rb))
    }
    var env ResponseEnvelope
    if err := json.Unmarshal(rb, &env); err != nil {
        return err
    }
    if env.Code != 1 {
        return fmt.Errorf("delete customer failed: %s", env.ErrMsg)
    }
    return nil
}

// GetReportsByClientId fetches reports for a client id
func (c *APIClient) GetReportsByClientId(clientId int64) ([]byte, error) {
    req := map[string]interface{}{"ClientId": clientId}
    status, rb, err := c.DoEncryptedRequest("/customer/SearchreportPageAndImagesV2", req)
    if err != nil {
        return nil, err
    }
    if status < 200 || status >= 300 {
        return nil, fmt.Errorf("get reports HTTP status %d: %s", status, string(rb))
    }
    return rb, nil
}

// GetReportImages retrieves images and temps for a report id
func (c *APIClient) GetReportImages(reportId string) ([]byte, error) {
    // The doc shows directly sending encrypted id; we'll send as {"Id": reportId}
    req := map[string]string{"Id": reportId}
    status, rb, err := c.DoEncryptedRequest("/customer/AsyncchotimagesByReportId", req)
    if err != nil {
        return nil, err
    }
    if status < 200 || status >= 300 {
        return nil, fmt.Errorf("get report images HTTP status %d: %s", status, string(rb))
    }
    return rb, nil
}

// SaveReportBatch implements SavereportApiV2_Batch (encrypted JSON payload)
func (c *APIClient) SaveReportBatch(payload interface{}) ([]byte, error) {
    status, rb, err := c.DoEncryptedRequest("/customer/SavereportApiV2_Batch", payload)
    if err != nil {
        return nil, err
    }
    if status < 200 || status >= 300 {
        return nil, fmt.Errorf("SaveReportBatch HTTP status %d: %s", status, string(rb))
    }
    return rb, nil
}

// Small wrapper for io.Copy to avoid importing io multiple times in apply_patch contexts
func ioCopy(dst io.Writer, src io.Reader) (int64, error) {
    return io.Copy(dst, src)
}
