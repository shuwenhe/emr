<?xml version="1.0" encoding="utf-8"?>
<TfrxReport Version="5.4.6" DotMatrixReport="False" IniFile="\Software\Fast Reports" PreviewOptions.Buttons="4095" PreviewOptions.Zoom="1" PrintOptions.Printer="??" PrintOptions.PrintOnSheet="0" ReportOptions.CreateDate="42651.686438125" ReportOptions.Description.Text="" ReportOptions.LastChange="43676.6522401852" ScriptLanguage="PascalScript" ScriptText.Text="&#13;&#10;procedure FooterQsItemBOnBeforePrint(Sender: TfrxComponent);&#13;&#10;begin&#13;&#10;  FooterQsItemB.Visible := (Trim(&#60;qslist.&#34;建议&#34;&#62;)&#60;&#62;'');&#13;&#10;end;&#13;&#10;&#13;&#10;procedure MemoPGS_signOnBeforePrint(Sender: TfrxComponent);&#13;&#10;begin&#13;&#10;  MemoPGS_sign.Visible := (Trim(&#60;评估医师&#62;)&#60;&#62;'');&#13;&#10;end;&#13;&#10;&#13;&#10;procedure MemoTelInfoOnBeforePrint(Sender: TfrxComponent);&#13;&#10;begin&#13;&#10;  MemoTelInfo.Visible := (Trim(&#60;电话&#62;) &#60;&#62; '');&#13;&#10;end;&#13;&#10;&#13;&#10;procedure FooterYzSummaryOnBeforePrint(Sender: TfrxComponent);&#13;&#10;begin&#13;&#10;  FooterYzSummary.Visible := (Trim(&#60;qslist.&#34;建议&#34;&#62;)&#60;&#62;'');&#13;&#10;end;&#13;&#10;&#13;&#10;begin&#13;&#10;&#13;&#10;end.">
  <Datasets>
    <item DataSet="frxDBDataset_exam" DataSetName="exam"/>
    <item DataSet="frxUserDataSet_imgtemprs" DataSetName="imgtemprs"/>
    <item DataSet="frxDBDataset_person" DataSetName="person"/>
    <item DataSet="frxDBDataset_qsgroup1" DataSetName="qsgroup1"/>
    <item DataSet="frxDBDataset_qsgroup2" DataSetName="qsgroup2"/>
    <item DataSetName="qsimgs"/>
    <item DataSet="frxDBDataset_qslist" DataSetName="qslist"/>
    <item DataSet="frxDBDataset_rpinfo" DataSetName="rpinfo"/>
  </Datasets>
  <Variables>
    <item Name=" 用户报表设置"/>
    <item Name="医院" Value="''"/>
    <item Name="LOGOFILE" Value="''"/>
    <item Name="DEVICE_ID" Value="''"/>
    <item Name="页眉" Value="''"/>
    <item Name="电话" Value="''"/>
    <item Name="地址" Value="''"/>
    <item Name="字体大小" Value="''"/>
    <item Name="图像大小" Value="''"/>
    <item Name="是否去掉背景" Value="'0'"/>
    <item Name="是否打印表格" Value="'0'"/>
    <item Name="评估医师" Value="''"/>
    <item Name="备注" Value="''"/>
    <item Name="报表风格" Value="'77A82BA1FE74472C97FC895FA6F94A94'"/>
  </Variables>
  <TfrxDataPage Name="Data" Height="1000" Left="0" Top="0" Width="1000"/>
  <TfrxReportPage Name="Page1" Font.Charset="134" Font.Color="0" Font.Height="-16" Font.Name="黑体" Font.Style="0" PaperWidth="210" PaperHeight="297" PaperSize="9" LeftMargin="10" RightMargin="10" TopMargin="10" BottomMargin="10" ColumnWidth="0" ColumnPositions.Text="" HGuides.Text="" VGuides.Text="">
    <TfrxMasterData Name="MasterDataGroupA" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="41.57483" Left="0" Top="638.74057" Width="718.1107" OnBeforePrint="MasterData1OnBeforePrint" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qsgroup1" DataSetName="qsgroup1" Filter="&#60;qsgroup1.&#34;级别&#34;&#62; = 2" PrintIfDetailEmpty="True" RowCount="0" Stretched="True">
      <TfrxShapeView Name="Shape5" Left="0" Top="11.3385899999998" Width="718.1107" Height="22.67718" Fill.BackColor="13408665" Frame.Color="13408665"/>
      <TfrxMemoView Name="MemoGroupTitleA" Left="11.33859" Top="15.1181200000001" Width="706.77211" Height="18.89765" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="134" Font.Color="16777215" Font.Height="-16" Font.Name="黑体" Font.Style="1" ParentFont="False" Text="[Line]、[qsgroup1.&#34;项目名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
    </TfrxMasterData>
    <TfrxMasterData Name="MasterDataBigImg" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="292.92146" Left="0" Top="196.53556" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qslist" DataSetName="qslist" Filter="&#60;qslist.&#34;项目名称&#34;&#62; = '热图显示区'" PrintChildIfInvisible="True" PrintIfDetailEmpty="True" RowCount="0">
      <TfrxPictureView Name="PictureBigImg" Left="109.60637" Top="3.77952999999999" Width="453.5436" Height="275.90569" Center="True" DataField="BigFileBlob1" DataSetName="qsimgs" HightQuality="False" Transparent="False" TransparentColor="16777215"/>
    </TfrxMasterData>
    <TfrxDetailData Name="DetailDataBigImgTempr" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="22.67718" Left="0" Top="593.38621" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxUserDataSet_imgtemprs" DataSetName="imgtemprs" RowCount="0">
      <TfrxShapeView Name="Shape4" Left="9.82677165354331" Top="0" Width="680.3154" Height="22.67718"/>
      <TfrxMemoView Name="MemoBIV_Id" Left="10.33859" Top="3.77953000000002" Width="170.07885" Height="18.8976378" HAlign="haCenter" Text="[imgtemprs.&#34;Name&#34;]"/>
      <TfrxMemoView Name="MemoBIV_Aver" Left="180.41744" Top="3.77953000000002" Width="170.07885" Height="18.89765" HAlign="haCenter" Text="[imgtemprs.&#34;Aver&#34;]"/>
      <TfrxMemoView Name="MemoBIV_Max" Left="350.49629" Top="3.77953000000002" Width="170.07885" Height="18.89765" HAlign="haCenter" Text="[imgtemprs.&#34;Max&#34;]"/>
      <TfrxMemoView Name="MemoBIV_Min" Left="520.57514" Top="3.77953000000002" Width="170.07885" Height="18.89765" HAlign="haCenter" Text="[imgtemprs.&#34;Min&#34;]"/>
      <TfrxLineView Name="Line6" Left="180.661417322835" Top="0" Width="0" Height="22.67718" Color="0" Frame.Typ="1"/>
      <TfrxLineView Name="Line7" Left="350.362204724409" Top="0" Width="0" Height="22.67718" Color="0" Frame.Typ="1"/>
      <TfrxLineView Name="Line8" Left="520.062992125984" Top="0" Width="0" Height="22.67718" Color="0" Frame.Typ="1"/>
    </TfrxDetailData>
    <TfrxPageFooter Name="PageFooter1" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="26.45671" Left="0" Top="1485.35529" Width="718.1107">
      <TfrxMemoView Name="MemoPageInfoA" Align="baCenter" Left="245.66945" Top="2" Width="226.7718" Height="15.11812" Font.Charset="134" Font.Color="0" Font.Height="-12" Font.Name="黑体" Font.Style="0" HAlign="haCenter" ParentFont="False" Text="Page [Page]/[TotalPages#]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxLineView Name="Line2" Left="0" Top="0" Width="721.89023" Height="0" Color="0" Frame.Color="12632256" Frame.Typ="4"/>
      <TfrxMemoView Name="MemoTelInfo" Left="498.89796" Top="2" Width="219.21274" Height="18.89765" OnBeforePrint="MemoTelInfoOnBeforePrint" Font.Charset="134" Font.Color="0" Font.Height="-13" Font.Name="黑体" Font.Style="0" HAlign="haRight" ParentFont="False" Text="咨询电话：[电话]"/>
    </TfrxPageFooter>
    <TfrxReportSummary Name="ReportSummary1" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="124.72449" Left="0" Top="1337.95362" Width="718.1107">
      <TfrxMemoView Name="MemoPGS_sign" Left="283.46475" Top="83.14966" Width="200.31509" Height="18.89765" OnBeforePrint="MemoPGS_signOnBeforePrint" Text="评估者签名：[评估医师]"/>
      <TfrxMemoView Name="MemoExamDate" Left="540.47279" Top="83.14966" Width="154.96073" Height="18.89765" Text="日期：[Date]"/>
    </TfrxReportSummary>
    <TfrxSubdetailData Name="SubdetailDataQsItem" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="37.7953" Left="0" Top="755.906" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qslist" DataSetName="qslist" FooterAfterEach="True" Filter="&#60;qslist.&#34;PID&#34;&#62; = &#60;qsgroup2.&#34;Id&#34;&#62;" PrintChildIfInvisible="True" PrintIfDetailEmpty="True" RowCount="0" Stretched="True">
      <TfrxMemoView Name="MemoQsImgTip" Left="41.57483" Top="15.1181200000002" Width="650.07916" Height="18.89765" StretchMode="smActualHeight" DataSet="frxDBDataset_qslist" DataSetName="qslist" WordBreak="True" Text="[qslist.&#34;图像提示&#34;]"/>
    </TfrxSubdetailData>
    <TfrxDetailData Name="DetailDataGroupB" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="30.23624" Left="0" Top="702.99258" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qsgroup2" DataSetName="qsgroup2" Filter="&#60;qsgroup2.&#34;PID&#34;&#62; = &#60;qsgroup1.&#34;ID&#34;&#62;" PrintIfDetailEmpty="True" RowCount="0">
      <TfrxMemoView Name="MemoGroupTitleB" Left="18.89765" Top="11.33859" Width="676.53587" Height="18.89765" DataSet="frxDBDataset_qsgroup2" DataSetName="qsgroup2" Text="[Line]) [qsgroup2.&#34;项目名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
    </TfrxDetailData>
    <TfrxDataBand4 Name="DataBandQsImgs" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="104.82684" Left="0" Top="865.51237" Width="718.1107" Columns="3" ColumnWidth="207.874015748031" ColumnGap="18.8976377952756" DataSetName="qsimgs" PrintChildIfInvisible="True" PrintIfDetailEmpty="True" RowCount="0">
      <TfrxPictureView Name="PictureQsItemImg" Left="52.91342" Top="2.77953000000002" Width="132.28355" Height="102.04731" DataField="FileBlob1" DataSetName="qsimgs" HightQuality="False" Transparent="False" TransparentColor="16777215"/>
    </TfrxDataBand4>
    <TfrxFooter Name="FooterQsItemB" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="26.45671" Left="0" Top="816.37848" Width="718.1107" OnBeforePrint="FooterQsItemBOnBeforePrint" Stretched="True">
      <TfrxMemoView Name="MemoQsSugg" Left="41.57483" Top="3.77953000000002" Width="650.07916" Height="18.89765" StretchMode="smActualHeight" DataSet="frxDBDataset_qslist" DataSetName="qslist" Text="建议：[qslist.&#34;建议&#34;]"/>
    </TfrxFooter>
    <TfrxHeader Name="HeaderBigImgTempr" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="55.5906" Left="0" Top="514.01608" Width="718.1107">
      <TfrxShapeView Name="Shape2" Left="0" Top="3.77953000000002" Width="718.1107" Height="22.67718" Fill.BackColor="13408665" Frame.Color="13408665"/>
      <TfrxMemoView Name="MemoBigImgTitle" Left="11.33859" Top="7.55906000000016" Width="706.77211" Height="18.89765" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="134" Font.Color="16777215" Font.Height="-16" Font.Name="黑体" Font.Style="1" ParentFont="False" Text="数据分析：">
        <Formats>
          <item/>
          <item/>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxShapeView Name="Shape3" Left="10" Top="32.9134200000001" Width="680.3154" Height="22.67718"/>
      <TfrxMemoView Name="MemoBIH_id" Left="10" Top="36.6929499999999" Width="170.07885" Height="18.8976378" HAlign="haCenter" Text="标识"/>
      <TfrxMemoView Name="MemoBIH_Aver" Left="180.07885" Top="36.6929499999999" Width="170.07885" Height="18.89765" HAlign="haCenter" Text="平均值"/>
      <TfrxMemoView Name="MemoBIH_Max" Left="350.1577" Top="36.6929499999999" Width="170.07885" Height="18.89765" HAlign="haCenter" Text="最大值"/>
      <TfrxMemoView Name="MemoBIH_Min" Left="520.23655" Top="36.6929499999999" Width="170.07885" Height="18.89765" HAlign="haCenter" Text="最小值"/>
      <TfrxLineView Name="Line3" Left="180.51979" Top="32.9134200000001" Width="0" Height="22.67718" Color="0" Frame.Typ="1"/>
      <TfrxLineView Name="Line4" Left="350.37817" Top="32.9134200000001" Width="0" Height="22.67718" Color="0" Frame.Typ="1"/>
      <TfrxLineView Name="Line5" Left="520.23655" Top="32.9134200000001" Width="0" Height="22.67718" Color="0" Frame.Typ="1"/>
    </TfrxHeader>
    <TfrxReportTitle Name="ReportTitle1" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="117.16543" Left="0" Top="18.89765" Width="718.1107">
      <TfrxShapeView Name="Shape1" Left="0" Top="94.48825" Width="718.1107" Height="22.67718" Fill.BackColor="13408665" Frame.Color="13408665"/>
      <TfrxMemoView Name="MemoRepTitle" Align="baWidth" Left="0" Top="11.33859" Width="718.1107" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-24" Font.Name="黑体" Font.Style="1" HAlign="haCenter" ParentFont="False" Text="[医院]"/>
      <TfrxMemoView Name="MemoPersonInfo" Left="11.33859" Top="98.26778" Width="706.77211" Height="18.89765" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="134" Font.Color="16777215" Font.Height="-16" Font.Name="黑体" Font.Style="1" ParentFont="False" Text="姓名：[person.&#34;患者名称&#34;]   性别：[person.&#34;性别&#34;]   年龄：[person.&#34;年龄&#34;]    项目：[exam.&#34;检查项目名称&#34;]">
        <Formats>
          <item/>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxMemoView Name="MemoRepSubTitle" Align="baWidth" Left="0" Top="49.13389" Width="718.1107" Height="18.89765" Font.Charset="134" Font.Color="0" Font.Height="-19" Font.Name="黑体" Font.Style="1" HAlign="haCenter" ParentFont="False" Text="红外热成像健康评估报告"/>
    </TfrxReportTitle>
    <TfrxMasterData Name="MasterDataYzSummary" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="86.92919" Left="0" Top="994.01639" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qslist" DataSetName="qslist" Filter="(&#60;qslist.&#34;项目名称&#34;&#62; =  '总结')" PrintIfDetailEmpty="True" RowCount="0" Stretched="True">
      <TfrxMemoView Name="Memo1" Left="41.57483" Top="56.6929500000001" Width="650.07916" Height="18.89765" StretchMode="smActualHeight" DataSet="frxDBDataset_qslist" DataSetName="qslist" WordBreak="True" Text="[qslist.&#34;图像提示&#34;]"/>
      <TfrxMemoView Name="Memo2" Left="18.89765" Top="22.67718" Width="676.53587" Height="18.89765" DataSet="frxDBDataset_qsgroup2" DataSetName="qsgroup2" Font.Charset="134" Font.Color="0" Font.Height="-19" Font.Name="黑体" Font.Style="1" ParentFont="False" Text="[qslist.&#34;项目名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
    </TfrxMasterData>
    <TfrxFooter Name="FooterYzSummary" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="41.57483" Left="0" Top="1103.62276" Width="718.1107" OnBeforePrint="FooterYzSummaryOnBeforePrint" Stretched="True">
      <TfrxMemoView Name="Memo3" Left="41.57483" Top="11.3385900000001" Width="650.07916" Height="18.89765" StretchMode="smActualHeight" DataSet="frxDBDataset_qslist" DataSetName="qslist" Text="建议：[qslist.&#34;建议&#34;]"/>
    </TfrxFooter>
    <TfrxDetailData Name="DetailDataYzSumImgs" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="109.60637" Left="0" Top="1167.87477" Width="718.1107" Columns="3" ColumnWidth="207.874015748031" ColumnGap="18.8976377952756" DataSetName="qsimgs" RowCount="0">
      <TfrxPictureView Name="Picture1" Left="52.91342" Top="3.77953000000002" Width="132.28355" Height="102.04731" DataField="FileBlob1" DataSetName="qsimgs" HightQuality="False" Transparent="False" TransparentColor="16777215"/>
    </TfrxDetailData>
  </TfrxReportPage>
</TfrxReport>
