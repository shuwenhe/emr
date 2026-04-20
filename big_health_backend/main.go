package main

import (
    "encoding/json"
    "fmt"
    "os"
)

func main() {
    server := os.Getenv("SERVER_URL")
    if server == "" {
        server = "http://qa.gddayo.com:5011"
    }
    account := os.Getenv("ACCOUNT")
    password := os.Getenv("PASSWORD")
    if account == "" || password == "" {
        fmt.Println("Please set ACCOUNT and PASSWORD environment variables or create credentials.env from credentials.example")
        return
    }

    client := NewAPIClient(server, account)

    fmt.Println("Logging in...")
    if err := client.Login(account, password, "demo-device"); err != nil {
        fmt.Printf("Login error: %v\n", err)
        return
    }
    fmt.Printf("Got ApiToken: %s\n", client.ApiToken)

    // Add a sample customer
    cust := Customer{RealName: "Demo User", Mobile: "13800138000", Age: 30}
    id, err := client.AddCustomer(cust)
    if err != nil {
        fmt.Printf("AddCustomer error: %v\n", err)
    } else {
        fmt.Printf("Added customer, id=%s\n", id)
    }

    // Search customers
    sr := SearchCustomersRequest{Mobile: "13800138000", PageIndex: 1, PageSize: 10}
    resp, err := client.SearchCustomers(sr)
    if err != nil {
        fmt.Printf("SearchCustomers error: %v\n", err)
    } else {
        b, _ := json.MarshalIndent(resp, "", "  ")
        fmt.Printf("Search result:\n%s\n", string(b))
    }

    // Try to fetch reports for a client id if we have one
    if len(resp.Customers) > 0 {
        // For demo use first customer's Id if numeric convertible, else skip
        fmt.Println("Attempting to fetch reports for first customer (skip if id not numeric)")
        // Use the customer Id field if present
        clientId := int64(0)
        // call GetReportsByClientId with 0 may return all
        rb, err := client.GetReportsByClientId(clientId)
        if err != nil {
            fmt.Printf("GetReportsByClientId error: %v\n", err)
        } else {
            fmt.Printf("Reports response:\n%s\n", Pretty(rb))
        }
    }

    // Note: GetReportImages and SaveReportV2 require known report ids or files.
    fmt.Println("Demo finished.")
}
