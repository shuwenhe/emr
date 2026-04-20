package main

import "encoding/json"

// Types and request/response structs for big_health_backend API

type ResponseEnvelope struct {
    Code    int             `json:"code"`
    Message string          `json:"message,omitempty"`
    ErrMsg  string          `json:"errMsg,omitempty"`
    Data    json.RawMessage `json:"data,omitempty"`
}

// Customer model (partial, per document)
type Customer struct {
    Id              string `json:"Id,omitempty"`
    RealName        string `json:"RealName"`
    Gender          string `json:"Gender,omitempty"`
    IdCard          string `json:"IdCard,omitempty"`
    Mobile          string `json:"Mobile"`
    Mobile2         string `json:"Mobile2,omitempty"`
    Mobile3         string `json:"Mobile3,omitempty"`
    RelativesMobile string `json:"RelativesMobile,omitempty"`
    Birthday        string `json:"Birthday,omitempty"`
    Address         string `json:"Address,omitempty"`
    MedicalRecord   string `json:"MedicalRecord,omitempty"`
    ThumbImage      string `json:"ThumbImage,omitempty"`
    HospitalDepartments int `json:"HospitalDepartments,omitempty"`
    Heigth          int    `json:"Heigth,omitempty"`
    Weight          int    `json:"Weight,omitempty"`
    ChiefComplaint  string `json:"ChiefComplaint,omitempty"`
    Remark          string `json:"Remark,omitempty"`
    Age             int    `json:"Age,omitempty"`
}

// Login request / response
type LoginRequest struct {
    Username string `json:"Username"`
    Password string `json:"Password"`
    DeviceSn string `json:"deviceSn"`
}

// Login response data structure (inside data)
type LoginData struct {
    Token string `json:"token"`
}

// Search customers request
type SearchCustomersRequest struct {
    Cid       int64  `json:"Cid,omitempty"`
    PageSize  int    `json:"PageSize,omitempty"`
    Mobile    string `json:"Mobile,omitempty"`
    PageIndex int    `json:"PageIndex,omitempty"`
    Start     string `json:"Start,omitempty"`
    End       string `json:"End,omitempty"`
}

// Search customers response
type SearchCustomersResponse struct {
    Customers []Customer `json:"Customers"`
    TotalCount int       `json:"TotalCount"`
    TotalPage  int       `json:"TotalPage"`
}
