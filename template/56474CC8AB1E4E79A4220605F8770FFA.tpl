<?xml version="1.0" encoding="utf-8"?>
<TfrxReport Version="5.4.6" DotMatrixReport="False" IniFile="\Software\Fast Reports" PreviewOptions.Buttons="4095" PreviewOptions.Zoom="1" PrintOptions.Printer="??" PrintOptions.PrintOnSheet="0" ReportOptions.CreateDate="42651.686438125" ReportOptions.Description.Text="" ReportOptions.LastChange="43836.5591566551" ScriptLanguage="PascalScript" ScriptText.Text="&#13;&#10;&#13;&#10;procedure DataBandQsImgsAOnBeforePrint(Sender: TfrxComponent);&#13;&#10;var&#13;&#10; ln: Integer;&#13;&#10;begin&#13;&#10;  ln := &#60;Line&#62;;&#13;&#10;  if ln in [1,3,5,7,9,11,13] then&#13;&#10;    ShapeImgBorderA.Visible := True&#13;&#10;  else&#13;&#10;    ShapeImgBorderA.Visible := False;&#13;&#10;end;&#13;&#10;&#13;&#10;begin&#13;&#10;&#13;&#10;end.">
  <Datasets>
    <item DataSet="frxDBDataset_exam" DataSetName="exam"/>
    <item DataSet="frxUserDataSet_imgtemprs" DataSetName="imgtemprs"/>
    <item DataSet="frxDBDataset_person" DataSetName="person"/>
    <item DataSet="frxDBDataset_qsgroup1" DataSetName="qsgroup1"/>
    <item DataSet="frxDBDataset_qsgroup2" DataSetName="qsgroup2"/>
    <item DataSet="frxDBDataset_qsgroup3" DataSetName="qsgroup3"/>
    <item DataSetName="qsimgs"/>
    <item DataSet="frxDBDataset_qslist" DataSetName="qslist"/>
    <item DataSet="frxDBDataset_rpinfo" DataSetName="rpinfo"/>
  </Datasets>
  <Variables>
    <item Name=" 用户报告设置"/>
    <item Name="医院" Value="''"/>
    <item Name="LOGOFILE" Value="''"/>
    <item Name="DEVICE_ID" Value="''"/>
    <item Name="页眉" Value="''"/>
    <item Name="电话" Value="''"/>
    <item Name="地址" Value="''"/>
    <item Name="字体大小" Value="''"/>
    <item Name="图像大小" Value="''"/>
    <item Name="是否去掉背景" Value="''"/>
    <item Name="是否打印表格" Value="''"/>
    <item Name="评估医师" Value="''"/>
    <item Name="备注" Value="''"/>
    <item Name="EXAM_LOGO_FILE"/>
  </Variables>
  <TfrxDataPage Name="Data" Height="1000" Left="0" Top="0" Width="1000"/>
  <TfrxReportPage Name="Cover" PaperWidth="210" PaperHeight="297" PaperSize="9" LeftMargin="10" RightMargin="10" TopMargin="10" BottomMargin="10" ColumnWidth="0" ColumnPositions.Text="" HGuides.Text="" VGuides.Text="" OnBeforePrint="CoverOnBeforePrint">
    <TfrxReportTitle Name="ReportTitle2" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="925.98485" Left="0" Top="18.89765" Width="718.1107" StartNewPage="True">
      <TfrxMemoView Name="Memo7" Align="baWidth" Left="0" Top="253.22851" Width="718.1107" Height="41.57483" Font.Charset="134" Font.Color="0" Font.Height="-32" Font.Name="黑体" Font.Style="1" HAlign="haCenter" ParentFont="False" Text="健 康 评 估 报 告"/>
      <TfrxMemoView Name="Memo6" Left="207.87415" Top="710.55164" Width="128.50402" Height="26.45671" Font.Charset="134" Font.Color="0" Font.Height="-14" Font.Name="黑体" Font.Style="1" HAlign="haRight" ParentFont="False" Text="姓　　名：">
        <Formats>
          <item/>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxMemoView Name="Memo9" Left="207.87415" Top="748.34694" Width="128.50402" Height="26.45671" Font.Charset="134" Font.Color="0" Font.Height="-14" Font.Name="黑体" Font.Style="1" HAlign="haRight" ParentFont="False" Text="性　　别："/>
      <TfrxMemoView Name="Memo10" Left="207.87415" Top="786.14224" Width="128.50402" Height="26.45671" Font.Charset="134" Font.Color="0" Font.Height="-14" Font.Name="黑体" Font.Style="1" HAlign="haRight" ParentFont="False" Text="年　　龄："/>
      <TfrxMemoView Name="Memo11" Left="207.87415" Top="823.93754" Width="128.50402" Height="26.45671" Font.Charset="134" Font.Color="0" Font.Height="-14" Font.Name="黑体" Font.Style="1" HAlign="haRight" ParentFont="False" Text="日　　期："/>
      <TfrxMemoView Name="Memo13" Left="347.71676" Top="710.55164" Width="128.50402" Height="26.45671" Font.Charset="134" Font.Color="0" Font.Height="-14" Font.Name="黑体" Font.Style="1" Frame.Typ="8" HAlign="haCenter" ParentFont="False" Text="[person.&#34;患者名称&#34;]"/>
      <TfrxMemoView Name="Memo14" Left="347.71676" Top="748.34694" Width="128.50402" Height="26.45671" Font.Charset="134" Font.Color="0" Font.Height="-14" Font.Name="黑体" Font.Style="1" Frame.Typ="8" HAlign="haCenter" ParentFont="False" Text="[person.&#34;性别&#34;]"/>
      <TfrxMemoView Name="Memo15" Left="347.71676" Top="786.14224" Width="128.50402" Height="26.45671" Font.Charset="134" Font.Color="0" Font.Height="-14" Font.Name="黑体" Font.Style="1" Frame.Typ="8" HAlign="haCenter" ParentFont="False" Text="[person.&#34;年龄&#34;]"/>
      <TfrxMemoView Name="Memo16" Left="347.71676" Top="823.93754" Width="128.50402" Height="18.89765" Font.Charset="134" Font.Color="0" Font.Height="-14" Font.Name="黑体" Font.Style="1" Frame.Typ="8" HAlign="haCenter" ParentFont="False" Text="[exam.&#34;createdate&#34;]"/>
      <TfrxLineView Name="Line1" Left="11.33859" Top="45.35436" Width="699.21305" Height="0" Color="8421504" Frame.Color="12632256" Frame.Typ="4" Frame.Width="2"/>
      <TfrxMemoView Name="Memo8" Left="94.48825" Top="166.29932" Width="529.13385827" Height="30.23624" Font.Charset="1" Font.Color="16711680" Font.Height="-32" Font.Name="黑体" Font.Style="1" HAlign="haCenter" ParentFont="False" Text="人体红外热图"/>
      <TfrxLineView Name="Line5" Left="11.33859" Top="668.97681" Width="699.21305" Height="0" Color="8421504" Frame.Typ="4"/>
      <TfrxMemoView Name="Memo5" Left="0" Top="319.10235" Width="717.00804" Height="47.89765" DataField="单位名称" DataSet="frxDBDataset_exam" DataSetName="exam" Font.Charset="1" Font.Color="0" Font.Height="-32" Font.Name="黑体" Font.Style="0" HAlign="haCenter" ParentFont="False" Text="[exam.&#34;单位名称&#34;]"/>
    </TfrxReportTitle>
  </TfrxReportPage>
  <TfrxReportPage Name="Page2" PaperWidth="210" PaperHeight="297" PaperSize="9" LeftMargin="10" RightMargin="10" TopMargin="10" BottomMargin="10" ColumnWidth="0" ColumnPositions.Text="" HGuides.Text="" VGuides.Text="">
    <TfrxPageHeader Name="PageHeader2" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="22.67718" Left="0" Top="18.89765" Width="718.1107">
      <TfrxMemoView Name="Memo19" Left="398.70099" Top="1.15748031" Width="315.63018" Height="18.89765" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" HAlign="haRight" ParentFont="False" Text="[exam.&#34;单位名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxMemoView Name="Memo12" Left="3.77953" Top="1.15748031" Width="429.07112" Height="18.89765" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="[person.&#34;患者名称&#34;]　[person.&#34;性别&#34;]　[person.&#34;年龄&#34;]     [exam.&#34;createdate&#34;]　">
        <Formats>
          <item/>
          <item/>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxLineView Name="Line6" Left="0" Top="21" Width="714.33117" Height="0" Color="8421504" Frame.Typ="4"/>
    </TfrxPageHeader>
    <TfrxMemoView Name="Memo23" Left="37.7953" Top="52.91342" Width="638.74057" Height="37.7953" Font.Charset="1" Font.Color="16711680" Font.Height="-24" Font.Name="Arial" Font.Style="1" HAlign="haCenter" ParentFont="False" Text="医用红外热成像技术"/>
    <TfrxMemoView Name="Memo28" Left="34.01577" Top="559.37044" Width="49.13389" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="1）*"/>
    <TfrxMemoView Name="Memo29" Left="83.14966" Top="559.37044" Width="260.78757" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="健康人群普查 "/>
    <TfrxMemoView Name="Memo30" Left="343.93723" Top="559.37044" Width="45.35436" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="2）*"/>
    <TfrxMemoView Name="Memo31" Left="389.29159" Top="559.37044" Width="283.46475" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="鼻炎、鼻窦炎（炎症 83.5%）"/>
    <TfrxMemoView Name="Memo32" Left="34.01577" Top="593.38621" Width="49.13389" Height="49.13389" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" WordWrap="False" VAlign="vaCenter" Text="3）*"/>
    <TfrxMemoView Name="Memo33" Left="83.14966" Top="593.38621" Width="260.78757" Height="49.13389" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" WordWrap="False" VAlign="vaCenter" Text="甲状腺疾病：甲状腺癌、甲状腺腺瘤、&#13;&#10;结节性甲状腺肿、甲状腺囊肿、甲状腺&#13;&#10;炎、甲亢"/>
    <TfrxMemoView Name="Memo34" Left="343.93723" Top="593.38621" Width="45.35436" Height="49.13389" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="4）*"/>
    <TfrxMemoView Name="Memo35" Left="389.29159" Top="593.38621" Width="283.46475" Height="49.13389" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="胃肠病变（与其他仪器比较 96%）：胃癌、胃&#13;&#10;炎、胃溃疡、结肠癌、慢性结肠炎"/>
    <TfrxMemoView Name="Memo36" Left="34.01577" Top="642.5201" Width="49.13389" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="5）"/>
    <TfrxMemoView Name="Memo37" Left="83.14966" Top="642.5201" Width="260.78757" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="肺癌"/>
    <TfrxMemoView Name="Memo38" Left="343.93723" Top="642.5201" Width="45.35436" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="6）*"/>
    <TfrxMemoView Name="Memo39" Left="389.29159" Top="642.5201" Width="283.46475" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="食道癌、食道炎"/>
    <TfrxMemoView Name="Memo40" Left="34.01577" Top="676.53587" Width="49.13389" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="7）"/>
    <TfrxMemoView Name="Memo41" Left="83.14966" Top="676.53587" Width="260.78757" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="冠心病：冠状动脉供血不足（91.8%）"/>
    <TfrxMemoView Name="Memo42" Left="343.93723" Top="676.53587" Width="45.35436" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="8）"/>
    <TfrxMemoView Name="Memo43" Left="389.29159" Top="676.53587" Width="283.46475" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="冠脉搭桥术手术过程监测"/>
    <TfrxMemoView Name="Memo44" Left="34.01577" Top="710.55164" Width="49.13389" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="9）"/>
    <TfrxMemoView Name="Memo45" Left="83.14966" Top="710.55164" Width="260.78757" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="颈椎病（20/21＝99%） "/>
    <TfrxMemoView Name="Memo46" Left="343.93723" Top="710.55164" Width="45.35436" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="10）*"/>
    <TfrxMemoView Name="Memo47" Left="389.29159" Top="710.55164" Width="283.46475" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="断指（趾）再植手术过程监测"/>
    <TfrxMemoView Name="Memo48" Left="34.01577" Top="744.56741" Width="49.13389" Height="56.69295" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="11）*"/>
    <TfrxMemoView Name="Memo49" Left="83.14966" Top="744.56741" Width="260.78757" Height="56.69295" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="乳腺病变：乳腺癌（90%）、乳腺纤维瘤&#13;&#10;（98%）、乳腺腺瘤、乳管内乳头状瘤、&#13;&#10;乳腺增生（85.1~94%）"/>
    <TfrxMemoView Name="Memo50" Left="343.93723" Top="744.56741" Width="45.35436" Height="56.69295" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="12）"/>
    <TfrxMemoView Name="Memo51" Left="389.29159" Top="744.56741" Width="283.46475" Height="56.69295" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="前列腺炎（临床诊断符合率 99.1%、前列腺&#13;&#10;常规检查符合率 87.4%、B 超符合率 99%）、&#13;&#10;精索静脉曲张"/>
    <TfrxMemoView Name="Memo52" Left="34.01577" Top="801.26036" Width="49.13389" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="13）"/>
    <TfrxMemoView Name="Memo53" Left="83.14966" Top="801.26036" Width="260.78757" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="强直性脊柱炎"/>
    <TfrxMemoView Name="Memo54" Left="343.93723" Top="801.26036" Width="45.35436" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="14）"/>
    <TfrxMemoView Name="Memo55" Left="389.29159" Top="801.26036" Width="283.46475" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="阑尾炎"/>
    <TfrxMemoView Name="Memo56" Left="34.01577" Top="835.27613" Width="49.13389" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="15）*"/>
    <TfrxMemoView Name="Memo57" Left="83.14966" Top="835.27613" Width="260.78757" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="宫颈炎、盆腔炎 "/>
    <TfrxMemoView Name="Memo58" Left="343.93723" Top="835.27613" Width="45.35436" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="16）"/>
    <TfrxMemoView Name="Memo59" Left="389.29159" Top="835.27613" Width="283.46475" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="皮肤癌"/>
    <TfrxMemoView Name="Memo24" Left="34.01577" Top="869.2919" Width="49.13389" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="17）*"/>
    <TfrxMemoView Name="Memo25" Left="83.14966" Top="869.2919" Width="260.78757" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="静脉曲张、血栓闭塞性脉管炎（下肢静&#13;&#10;脉病 85~90%）"/>
    <TfrxMemoView Name="Memo26" Left="343.93723" Top="869.2919" Width="45.35436" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="18）"/>
    <TfrxMemoView Name="Memo27" Left="389.29159" Top="869.2919" Width="283.46475" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="宋体" Font.Style="0" Frame.Typ="15" ParentFont="False" VAlign="vaCenter" Text="肝癌、肝炎、脂肪肝、酒精肝、肝硬化（肝&#13;&#10;病 70~85%）等。"/>
    <TfrxRichView Name="Rich1" Left="18.89765" Top="109.60637" Width="661.41775" Height="445.98454" GapX="2" GapY="1" PropData="0852696368456469740A341600007B5C727466315C616E73695C616E73696370673933365C64656666305C6E6F7569636F6D7061745C6465666C616E67313033335C6465666C616E676665323035327B5C666F6E7474626C7B5C66305C666E696C5C6663686172736574313334205C2763625C2763655C2763635C2765353B7D7D0D0A7B5C2A5C67656E657261746F722052696368656432302031302E302E31373736337D5C766965776B696E64345C756331200D0A5C706172645C625C66305C667332325C6C616E67323035325C2764325C2762625C2761315C2761325C2764325C2762645C2764335C2763335C2762615C2765635C2763645C2765325C2763385C2763385C2763665C2766315C2764325C2763375C2762355C2763345C2764325C2762645C2764315C2761375C2764345C2761645C2763305C2765645C2761335C2762615C62305C7061720D0A5C2761315C2761315C2761315C2761315C2762355C2762315C2763385C2763625C2763635C2765355C2763395C2766615C2763305C2765645C2764375C2762345C2762665C2766365C2763365C2766305C2763315C2763625C2762315C2765345C2762625C2761665C2762625C2766325C2762375C2761325C2763395C2766615C2762325C2761315C2762315C2765345C2763615C2762315C2761335C2761385C2762305C2766635C2763305C2761385C2763635C2765355C2762315C2765645C2762325C2761315C2762315C2765345C2762615C2763645C2763635C2765355C2763345C2764615C2762325C2761315C2762315C2765345C2761335C2761395C2761335C2761635C2764345C2764615C2762385C2766375C2764365C2764365C2763395C2766615C2763305C2765645C2762625C2766325C2762325C2761315C2763305C2765645C2762625C2766615C2764365C2763365C2762355C2763345C2764375C2766375C2764335C2763335C2763665C2763325C2761335C2761635C2763385C2763625C2763635C2765355C2763665C2765305C2764335C2761365C2762325C2762665C2763655C2762625C2762355C2763345C2762345C2766615C2764305C2762625C2762385C2763345C2762315C2765345C2761335C2761635C2763655C2763325C2762365C2763385C2763625C2765365C2764365C2761655C2762375C2761325C2763395C2766615C2764335C2765625C2764355C2766645C2762335C2761335C2762625C2766325C2762385C2764665C2762625C2766325C2762355C2763645C2762355C2763345C2763365C2761625C2763305C2765625C2761335C2761635C2762645C2761625C2764355C2765325C2763615C2762315C2762325C2763395C2762635C2761665C2762355C2762645C2762355C2763345C2762615C2765635C2763645C2765325C2763385C2763385C2763645C2762635C2764335C2765625C2764355C2766645C2762335C2761335C2763385C2763625C2763635C2765355C2762615C2765635C2763645C2765325C2763385C2763385C2763645C2762635C2762645C2766385C2764305C2764305C2762365C2764345C2762315C2763385C2762615C2763645C2762375C2764365C2763655C2766365C2761335C2761635C2762655C2763645C2762665C2763395C2762375C2762345C2764335C2762335C2763385C2763625C2763635C2765355C2762645C2761315C2762665C2762355C2764375C2762345C2762665C2766365C2761335C2761635C2763655C2761615C2763315C2764395C2762345C2762325C2764325C2762645C2763615C2761365C2764355C2765665C2762365C2763665C2762635C2762325C2762325C2761315C2763635C2765315C2762395C2761395C2764365C2764385C2764325C2761615C2764325C2763305C2762655C2764645C2761315C2761335C7061720D0A5C7061720D0A5C625C2762365C2766655C2761315C2761325C2764335C2763335C2763645C2762655C2761335C2762615C62305C7061720D0A5C2761315C2761315C2761315C2761315C2762315C2762655C2762635C2762635C2763615C2766355C2763615C2763615C2764335C2763335C2764335C2764615C2764325C2766645C2763365C2766305C2763655C2763325C2762365C2763385C2762385C2763345C2762315C2765345C2762355C2763345C2762635C2765635C2762325C2765325C2761335C2761635C2762665C2763395C2764335C2763335C2764335C2764615C2763385C2763625C2763635C2765355C2762365C2765305C2764365C2764365C2764375C2765395C2764365C2761665C2762635C2762305C2763365C2766375C2762395C2764395C2762355C2763345C2764315C2764375C2764365C2761325C2761315C2761325C2764365C2764375C2763315C2766365C2761315C2761325C2762345C2766615C2764305C2762625C2764325C2765635C2762335C2761335C2762635C2762305C2764315C2761615C2762395C2764635C2762635C2762325C2762325C2761315C2762355C2763345C2762385C2761385C2764365C2766615C2764355C2765665C2762365C2763665C2761335C2761635C2764325C2762325C2762665C2763395C2764335C2763335C2764335C2764615C2764325C2762645C2764315C2761375C2762665C2763365C2764315C2764305C2762635C2762305C2762645C2763635C2764315C2761375C2761315C2761335C7061720D0A5C7061720D0A5C625C2763385C2766645C2761315C2761325C2763635C2764385C2762355C2765335C2761335C2762615C62305C7061720D0A5C2761315C2761315C2761315C276131315C2761335C2761395C2764305C2763325C2761335C2762615C2764325C2762645C2764335C2763335C2762615C2765635C2763645C2765325C2763385C2763385C2762335C2763395C2763665C2766315C2762635C2762635C2763615C2766355C2763345C2764635C2762305C2764315C2763385C2763625C2763635C2765355C2762655C2764365C2762325C2762665C2763655C2763325C2762365C2763385C2762375C2764365C2762325C2762635C2762355C2763345C2764305C2763355C2763665C2761325C2762635C2763375C2763325C2762635C2762325C2761325C2763665C2764345C2763615C2762655C2764345C2764615C2764325C2762625C2764355C2763355C2763365C2762645C2763335C2765365C2763645C2762635C2763395C2763665C2761335C2761635C2762635C2762385C2764355C2763355C2762325C2762625C2763645C2761635C2762325C2765305C2763335C2765365C2762355C2763345C2762615C2765635C2763645C2765325C2763385C2763385C2763645C2762635C2762635C2762345C2762665C2763395C2762395C2762395C2762335C2763395C2763645C2765615C2764355C2766625C2762355C2763345C2763385C2763625C2763635C2765355C2763385C2763385C2762375C2764365C2762325C2762635C2764375C2762345C2763635C2761635C2761335C2761635C2764355C2765325C2762655C2763645C2763655C2761615C2764325C2762645C2764315C2761375C2764315C2764305C2762655C2762665C2762635C2762325C2762325C2761315C2763635C2765315C2762395C2761395C2763315C2763625C2764325C2762625C2762385C2766365C2763385C2761625C2764305C2763325C2762355C2763345C2763385C2763385C2762375C2764365C2762325C2762635C2762645C2763375C2762365C2763385C2761315C2761335C7061720D0A5C2761315C2761315C2761315C276131325C2761335C2761395C2764345C2765375C2761335C2762615C2763655C2764655C2763325C2764625C2763615C2763375C2763385C2763625C2763635C2765355C2762355C2763345C2763395C2766615C2763305C2765645C2764375C2762345C2762665C2766365C2762375C2761325C2763395C2766615C2762315C2765345C2762625C2761665C2761335C2761635C2762625C2762395C2763615C2763375C2762635C2762325C2762325C2761315C2762355C2763345C2762325C2766615C2763395C2766615C2761335C2761635C2762365C2762635C2762625C2765315C2764325C2766645C2763365C2766305C2763655C2763325C2762365C2763385C2762335C2761315C2762355C2763345C2762385C2763345C2762315C2765345C2761315C2761335C2762615C2765635C2763645C2765325C2763385C2763385C2763665C2766315C2764325C2763375C2762355C2763345C2762325C2765325C2763655C2763325C2763315C2765395C2763335C2766345C2762365C2763385C2762635C2761625C2762385C2764665C2761335C2761635C2763345C2764635C2763335C2765385C2762635C2763375C2762355C2763645C2764335C27646120302E30355C2761315C2765365C2763665C2762385C2763655C2761325C2763655C2763325C2762365C2763385C2762315C2765345C2762625C2761665C2761335C2761635C2764365C2762315C2762395C2764625C2762355C2764385C2762375C2762345C2764335C2762335C2762335C2766365C2763385C2763625C2763635C2765355C2764325C2765635C2762335C2761335C2763655C2763325C2763375C2766385C2761315C2761335C2764355C2765325C2764345C2764615C2762635C2762325C2762325C2761315C2764345C2765375C2763365C2764615C2761335C2761635C2762645C2766365C2764335C2764305C2762395C2761365C2763345C2764635C2764305C2764345C2761335C2761385C2762635C2762345C2762345C2766615C2764305C2762625C2761335C2761395C2762385C2763345C2762315C2765345C2762365C2766385C2763395C2764305C2763655C2762345C2764305C2763655C2762335C2763395C2763365C2766375C2764365C2763615C2764305C2764345C2762325C2761315C2762315C2765345C2763615C2762315C2761335C2761635C2764335C2763385C2763365C2765345C2764335C2764305C2764325C2765325C2764325C2765355C2761315C2761335C2763625C2766395C2763655C2762645C6C64626C71756F74655C2763655C2763325C2762315C2765345C2764345C2765375C2764335C2764615C2762325C2761315C2762315C2765345C7264626C71756F74655C2761335C2761635C2763645C2761385C2762395C2766645C2764325C2762645C2764335C2763335C2762615C2765635C2763645C2765325C2763385C2763385C2762335C2763395C2763665C2766315C2762635C2762635C2763615C2766355C2762325C2763395C2762635C2761665C2763655C2763325C2762365C2763385C2762315C2765345C2762625C2761665C2762355C2763345C2764305C2763355C2763665C2761325C2761335C2761635C2762665C2763395C2763635C2765315C2764345C2765375C2762375C2761325C2763665C2764365C2764315C2766345C2764305C2764345C2762385C2763345C2762315C2765345C2761335C2761635C2762365C2764345C2763385C2763625C2763635C2765355C2762645C2761315C2762665C2762355C2764335C2764305C2764375C2763355C2764345C2761345C2762655C2761665C2764375C2766375C2764335C2763335C2761315C2761335C7061720D0A5C2761315C2761315C2761315C276131335C2761335C2761395C2763325C2763635C2763395C2761625C2763635C2765355C2762635C2765635C2761335C2762615C2764325C2762645C2764335C2763335C2762615C2765635C2763645C2765325C2763385C2763385C2762335C2763395C2763665C2766315C2762635C2762635C2763615C2766355C2762325C2762625C2762375C2761325C2762335C2766365C2762375C2766385C2763395C2765345C2761335C2761635C2762365C2766385C2763615C2763375C2763645C2761385C2762395C2766645C2762615C2765635C2763645C2765325C2763635C2762645C2762325C2765325C2763365C2766375C2762315C2762625C2762365C2761665C2762355C2764385C2762645C2764335C2763615C2764355C2763385C2763625C2763635C2765355C2763665C2766325C2763645C2765325C2762375C2761325C2763395C2765345C2762355C2763345C2762615C2765635C2763645C2765325C2763665C2764665C2761315C2761335C2763645C2761635C2763615C2762315C2762365C2764345C2763385C2763625C2763635C2765355C2763655C2764655C2763385C2763655C2762615C2763655C2763625C2766305C2762615C2761365C2762615C2763645C2762385C2762315C2764375C2766375C2764335C2763335C2761315C2761325C2763655C2764655C2764305C2765385C2762315C2765615C2762635C2763375C2764325C2761395C2763655C2765665C2761335C2761635C2762665C2763395C2764345C2764615C2762365C2764345C2763645C2761635C2764325C2762625C2762635C2762325C2762325C2761315C2762615C2763645C2763635C2765355C2762635C2765635C2764355C2764665C2762645C2766385C2764305C2764305C2762325C2761315C2763375C2765395C2764375C2762375C2764375C2764395C2762615C2763645C2763315C2763365C2764305C2761375C2762395C2764625C2762325C2765635C2763615C2762315C2762365C2765305C2762345C2763655C2761315C2761325C2762375C2762345C2762385C2762345C2762355C2764385C2762645C2766385C2764305C2764305C2762635C2765635C2762325C2765395C2761335C2761635C2763615C2763375C2764355C2765365C2764355C2766645C2762355C2763345C2763325C2763635C2763395C2761625C2763635C2765355C2762635C2765635C2761315C2761335C2764375C2766375C2763655C2761615C2762395C2761365C2763345C2764635C2764305C2764345C2764335C2762305C2763665C2766315C2764355C2765665C2762365C2763665C2763395C2765385C2762315C2762385C2761335C2761635C2763365C2765345C2762635C2765635C2764315C2765395C2762645C2765315C2762395C2766625C2762665C2763395C2764335C2765625C2762305C2766635C2763305C2761382058205C2762395C2765325C2761315C27613242205C2762335C2761635C2761315C2761324354205C2762355C2763385C2762645C2765315C2762395C2762395C2764305C2764345C2764335C2762305C2763665C2766315C2764355C2765665C2762365C2763665C2763395C2765385C2762315C2762385C2764345C2764615C2763345C2764615C2762355C2763345C2762635C2765635C2762325C2765395C2762315C2761385C2762385C2765365C2763665C2765305C2762625C2761355C2762325C2762395C2762335C2765345C2761315C2761325C2763665C2765305C2762625C2761355C2762645C2765385C2762635C2766385C2761315C2761335C7061720D0A5C7061720D0A5C625C2763625C2763345C2761315C2761325C2763315C2764395C2762345C2762325C2764335C2761365C2764335C2763335C2762375C2762365C2763655C2761375C2764335C2765625C2762325C2762665C2762375C2764365C2763315C2764395C2762345C2762325C2764355C2765665C2762365C2763665C2762375C2766625C2762615C2763665C2763325C2763615C2761335C276138202A5C2763655C2761615C2764335C2763355C2763615C2763365C2764335C2761365C2764335C2763335C2762375C2762365C2763655C2761375C2761335C2761395C62305C7061720D0A7D0D0A00"/>
  </TfrxReportPage>
  <TfrxReportPage Name="Page3" PaperWidth="210" PaperHeight="297" PaperSize="9" LeftMargin="10" RightMargin="10" TopMargin="10" BottomMargin="10" ColumnWidth="0" ColumnPositions.Text="" HGuides.Text="" VGuides.Text="">
    <TfrxPageHeader Name="PageHeader3" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="22.67718" Left="0" Top="18.89765" Width="718.1107">
      <TfrxMemoView Name="Memo62" Left="407.48052" Top="1" Width="307.85065" Height="18.89765" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" HAlign="haRight" ParentFont="False" Text="[exam.&#34;单位名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxMemoView Name="Memo64" Left="4.77953" Top="1" Width="431.85065" Height="18.89765" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="[person.&#34;患者名称&#34;]　[person.&#34;性别&#34;]　[person.&#34;年龄&#34;]     [exam.&#34;createdate&#34;]　">
        <Formats>
          <item/>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxLineView Name="Line7" Left="1" Top="20.84251969" Width="714.33117" Height="0" Color="8421504" Frame.Typ="4"/>
    </TfrxPageHeader>
    <TfrxHeader Name="HeaderP3" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="79.37013" Left="0" Top="102.04731" Width="718.1107">
      <TfrxMemoView Name="Memo67" Left="22.67718" Top="41.57483" Width="241.88992" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-19" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="红外热成像仪扫描所见："/>
    </TfrxHeader>
    <TfrxMasterData Name="MasterData1" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="5.67718" Left="0" Top="204.09462" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qslist" DataSetName="qslist" Filter="&#60;qslist.&#34;项目名称&#34;&#62; = '热图显示区'" PrintChildIfInvisible="True" PrintIfDetailEmpty="True" RowCount="0"/>
    <TfrxDetailData Name="DetailData2" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="362.83488" Left="0" Top="234.33086" Width="718.1107" Columns="2" ColumnWidth="340.157480314961" ColumnGap="15.1181102362205" DataSetName="qsimgs" RowCount="0">
      <TfrxPictureView Name="Picture1" Left="11.33859" Top="7.55906" Width="309.92146" Height="336.37817" Center="True" DataField="BigFileBlob1" DataSetName="qsimgs" HightQuality="False" Transparent="False" TransparentColor="16777215"/>
    </TfrxDetailData>
  </TfrxReportPage>
  <TfrxReportPage Name="PageD1" Font.Charset="134" Font.Color="0" Font.Height="-16" Font.Name="黑体" Font.Style="0" PaperWidth="210" PaperHeight="297" PaperSize="256" LeftMargin="10" RightMargin="10" TopMargin="10" BottomMargin="10" ColumnWidth="0" ColumnPositions.Text="" HGuides.Text="" VGuides.Text="" OnBeforePrint="Page1OnBeforePrint">
    <TfrxMasterData Name="MasterDataGroupA1" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="64.25201" Left="0" Top="102.04731" Width="718.1107" OnBeforePrint="MasterData1OnBeforePrint" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qsgroup1" DataSetName="qsgroup1" Filter="&#60;qsgroup1.&#34;级别&#34;&#62; = 2" PrintIfDetailEmpty="True" RowCount="0" Stretched="True">
      <TfrxShapeView Name="Shape5" Left="22.67718" Top="18.89765" Width="627.40198" Height="45.35436" Frame.BottomLine.Color="16777215"/>
      <TfrxMemoView Name="MemoGroupTitleA1" Left="26.45671" Top="30.23624" Width="306.14193" Height="26.45671" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="134" Font.Color="0" Font.Height="-16" Font.Name="黑体" Font.Style="1" ParentFont="False" VAlign="vaCenter" Text="　[Line]、[qsgroup1.&#34;项目名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
    </TfrxMasterData>
    <TfrxSubdetailData Name="SubdetailDataQsGroupB2" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="30.23624" Left="0" Top="468.66172" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qsgroup3" DataSetName="qsgroup3" FooterAfterEach="True" Filter="&#60;qsgroup3.&#34;PID&#34;&#62; = &#60;qsgroup2.&#34;Id&#34;&#62;" PrintChildIfInvisible="True" PrintIfDetailEmpty="True" RowCount="0" Stretched="True">
      <TfrxMemoView Name="MemoGroupTitleB1" Left="22.67718" Top="0" Width="627.4015748" Height="30.23624" DataSet="frxDBDataset_qsgroup2" DataSetName="qsgroup2" Font.Charset="134" Font.Color="0" Font.Height="-15" Font.Name="黑体" Font.Style="0" Frame.Typ="11" ParentFont="False" WordBreak="True" VAlign="vaCenter" Text="　　● [qsgroup3.&#34;项目名称&#34;]"/>
    </TfrxSubdetailData>
    <TfrxDetailData Name="DetailDataGroupB1" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="0" Left="0" Top="445.98454" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qsgroup2" DataSetName="qsgroup2" Filter="&#60;qsgroup2.&#34;PID&#34;&#62; = &#60;qsgroup1.&#34;ID&#34;&#62;" PrintIfDetailEmpty="True" RowCount="0"/>
    <TfrxPageHeader Name="PageHeader1" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="22.67718" Left="0" Top="18.89765" Width="718.1107">
      <TfrxMemoView Name="Memo133" Left="414.81911" Top="1" Width="300.51206" Height="18.89765" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" HAlign="haRight" ParentFont="False" Text="[exam.&#34;单位名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxMemoView Name="Memo134" Left="4.77953" Top="1" Width="450.40971" Height="18.89765" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="[person.&#34;患者名称&#34;]　[person.&#34;性别&#34;]　[person.&#34;年龄&#34;]     [exam.&#34;createdate&#34;]　">
        <Formats>
          <item/>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxLineView Name="Line3" Left="1" Top="20.84251969" Width="714.33117" Height="0" Color="8421504" Frame.Typ="4"/>
    </TfrxPageHeader>
    <TfrxDetailData Name="DetailData1" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="0" Left="0" Top="188.9765" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qslist" DataSetName="qslist" Filter="&#60;qslist.&#34;ID&#34;&#62; = &#60;qsgroup1.&#34;ID&#34;&#62;" RowCount="0"/>
    <TfrxSubdetailData Name="DataBandQsImgsA" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="210.65368" Left="0" Top="211.65368" Width="718.1107" OnBeforePrint="DataBandQsImgsAOnBeforePrint" Columns="2" ColumnWidth="226.771653543307" ColumnGap="18.8976377952756" DataSetName="qsimgs" PrintChildIfInvisible="True" PrintIfDetailEmpty="True" RowCount="0">
      <TfrxShapeView Name="ShapeImgBorderA" Left="22.67718" Top="0" Width="627.40198" Height="210.51974118" Frame.Typ="3"/>
      <TfrxPictureView Name="PictureQsItemImg" Left="41.57483" Top="10.33859" Width="181.41744" Height="185.19697" DataField="FileBlob1" DataSetName="qsimgs" HightQuality="False" Transparent="False" TransparentColor="16777215"/>
    </TfrxSubdetailData>
  </TfrxReportPage>
  <TfrxReportPage Name="PageD2" PaperWidth="210" PaperHeight="297" PaperSize="9" LeftMargin="10" RightMargin="10" TopMargin="10" BottomMargin="10" ColumnWidth="0" ColumnPositions.Text="" HGuides.Text="" VGuides.Text="">
    <TfrxPageHeader Name="PageHeader7" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="22.67718" Left="0" Top="18.89765" Width="718.1107">
      <TfrxMemoView Name="Memo141" Left="416.70099" Top="1" Width="298.63018" Height="18.89765" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" HAlign="haRight" ParentFont="False" Text="[exam.&#34;单位名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxMemoView Name="Memo142" Left="4.77953" Top="1" Width="447.30736" Height="18.89765" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="[person.&#34;患者名称&#34;]　[person.&#34;性别&#34;]　[person.&#34;年龄&#34;]     [exam.&#34;createdate&#34;]　">
        <Formats>
          <item/>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxLineView Name="Line2" Left="1" Top="20.84251969" Width="714.33117" Height="0" Color="8421504" Frame.Typ="4"/>
    </TfrxPageHeader>
    <TfrxMasterData Name="MasterDataGroupA" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="41.57483" Left="0" Top="192.75603" Width="718.1107" OnBeforePrint="MasterData1OnBeforePrint" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qsgroup1" DataSetName="qsgroup1" Filter="&#60;qsgroup1.&#34;级别&#34;&#62; = 3" PrintIfDetailEmpty="True" RowCount="0" Stretched="True">
      <TfrxShapeView Name="Shape2" Left="0" Top="11.3385899999998" Width="718.1107" Height="22.67718" Fill.BackColor="13408665" Frame.Color="13408665"/>
      <TfrxMemoView Name="MemoGroupTitleA" Left="11.33859" Top="15.1181200000001" Width="706.77211" Height="18.89765" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="134" Font.Color="16777215" Font.Height="-16" Font.Name="黑体" Font.Style="1" ParentFont="False" Text="[Line]、[qsgroup1.&#34;项目名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
    </TfrxMasterData>
    <TfrxSubdetailData Name="SubdetailDataQsItem" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="37.7953" Left="0" Top="309.92146" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qslist" DataSetName="qslist" FooterAfterEach="True" Filter="&#60;qslist.&#34;PID&#34;&#62; = &#60;qsgroup2.&#34;Id&#34;&#62;" PrintChildIfInvisible="True" PrintIfDetailEmpty="True" RowCount="0" Stretched="True">
      <TfrxMemoView Name="MemoQsImgTip" Left="41.57483" Top="15.11812" Width="650.07916" Height="18.89765" StretchMode="smActualHeight" DataSet="frxDBDataset_qslist" DataSetName="qslist" WordBreak="True" Text="[qslist.&#34;图像提示&#34;]"/>
    </TfrxSubdetailData>
    <TfrxDetailData Name="DetailDataGroupB" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="30.23624" Left="0" Top="257.00804" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qsgroup2" DataSetName="qsgroup2" Filter="&#60;qsgroup2.&#34;PID&#34;&#62; = &#60;qsgroup1.&#34;ID&#34;&#62;" PrintIfDetailEmpty="True" RowCount="0">
      <TfrxMemoView Name="MemoGroupTitleB" Left="18.89765" Top="11.33859" Width="676.53587" Height="18.89765" DataSet="frxDBDataset_qsgroup2" DataSetName="qsgroup2" Text="[Line]) [qsgroup2.&#34;项目名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
    </TfrxDetailData>
    <TfrxFooter Name="FooterQsItemB" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="26.45671" Left="0" Top="370.39394" Width="718.1107" Stretched="True">
      <TfrxMemoView Name="MemoQsSugg" Left="41.57483" Top="3.77953" Width="650.07916" Height="18.89765" StretchMode="smActualHeight" DataSet="frxDBDataset_qslist" DataSetName="qslist" Text="建议：[qslist.&#34;建议&#34;]"/>
    </TfrxFooter>
    <TfrxMasterData Name="MasterDataYzSummary" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="86.92919" Left="0" Top="419.52783" Width="718.1107" ColumnWidth="0" ColumnGap="0" DataSet="frxDBDataset_qslist" DataSetName="qslist" Filter="(&#60;qslist.&#34;项目名称&#34;&#62; =  '总结')" RowCount="0" Stretched="True">
      <TfrxMemoView Name="Memo1" Left="41.57483" Top="56.69295" Width="650.07916" Height="18.89765" StretchMode="smActualHeight" DataSet="frxDBDataset_qslist" DataSetName="qslist" WordBreak="True" Text="[qslist.&#34;图像提示&#34;]"/>
      <TfrxMemoView Name="Memo2" Left="18.89765" Top="22.67718" Width="676.53587" Height="18.89765" DataSet="frxDBDataset_qsgroup2" DataSetName="qsgroup2" Font.Charset="134" Font.Color="0" Font.Height="-19" Font.Name="黑体" Font.Style="1" ParentFont="False" Text="[qslist.&#34;项目名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
    </TfrxMasterData>
    <TfrxFooter Name="FooterYzSummary" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="41.57483" Left="0" Top="529.1342" Width="718.1107" Stretched="True">
      <TfrxMemoView Name="Memo3" Left="41.57483" Top="11.33859" Width="650.07916" Height="18.89765" StretchMode="smActualHeight" DataSet="frxDBDataset_qslist" DataSetName="qslist" Text="建议：[qslist.&#34;建议&#34;]"/>
    </TfrxFooter>
    <TfrxHeader Name="Header1" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="68.03154" Left="0" Top="102.04731" Width="718.1107">
      <TfrxMemoView Name="Memo4" Left="207.87415" Top="30.23624" Width="287.24428" Height="30.23624" Font.Charset="134" Font.Color="0" Font.Height="-21" Font.Name="黑体" Font.Style="1" HAlign="haCenter" ParentFont="False" VAlign="vaCenter" Text="红外热成像健康评估"/>
    </TfrxHeader>
  </TfrxReportPage>
  <TfrxReportPage Name="Page4" PaperWidth="210" PaperHeight="297" PaperSize="9" LeftMargin="10" RightMargin="10" TopMargin="10" BottomMargin="10" ColumnWidth="0" ColumnPositions.Text="" HGuides.Text="" VGuides.Text="">
    <TfrxMemoView Name="Memo97" Left="109.60637" Top="60.47248" Width="495.11843" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-19" Font.Name="Arial" Font.Style="1" HAlign="haCenter" ParentFont="False" Text="部分术语解释"/>
    <TfrxMemoView Name="Memo98" Left="37.7953" Top="113.3859" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="血压、血糖升高或降低趋势"/>
    <TfrxMemoView Name="Memo99" Left="37.7953" Top="139.84261" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="您的血压、血糖已经开始出现异常，但还未达到临床异常批标的范围，或正处于临界，应引起您的关注。"/>
    <TfrxMemoView Name="Memo100" Left="37.7953" Top="166.29932" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="尿酸升高趋势"/>
    <TfrxMemoView Name="Memo101" Left="37.7953" Top="192.75603" Width="646.29963" Height="22.67718" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="您的嘌呤代谢已经开始出现异常，但此地并不一定未出现明显的症状和临床检验指标。"/>
    <TfrxMemoView Name="Memo102" Left="37.7953" Top="215.43321" Width="646.29963" Height="22.67718" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="XX 疾病或 X XX 疾病（史）"/>
    <TfrxMemoView Name="Memo103" Left="37.7953" Top="238.11039" Width="646.29963" Height="41.57483" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="由于手术后，在相当长的一段时间内，手术部位表现为代谢热增高，与手术前的疾病表现相似，在没有了&#13;&#10;解病史前，应不能排除有手术史。"/>
    <TfrxMemoView Name="Memo104" Left="37.7953" Top="279.68522" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="***功能异常"/>
    <TfrxMemoView Name="Memo105" Left="37.7953" Top="306.14193" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="***一般指某脏器，批示功能异常说明该脏器代谢异常，并不排除切除所带来的功能改变。"/>
    <TfrxMemoView Name="Memo106" Left="37.7953" Top="332.59864" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="激素损伤"/>
    <TfrxMemoView Name="Memo107" Left="37.7953" Top="359.05535" Width="646.29963" Height="41.57483" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="长期服用保健品及激素类药物；食用含激素食品等均可导致不同程度的激素损伤，从而引起甲状腺、乳腺、&#13;&#10;子宫或卵巢等器官代谢热的异常。"/>
    <TfrxMemoView Name="Memo108" Left="37.7953" Top="400.63018" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="不除外 ……"/>
    <TfrxMemoView Name="Memo109" Left="37.7953" Top="427.08689" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="由于某些疾病有共同的代谢热反映，不除外……即表示 XX 疾病的可能性最大。"/>
    <TfrxMemoView Name="Memo110" Left="37.7953" Top="453.5436" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="肺污染状态"/>
    <TfrxMemoView Name="Memo111" Left="37.7953" Top="480.00031" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="长期吸烟或处于空气污浊的环境中，均可导致肺污染。"/>
    <TfrxMemoView Name="Memo112" Left="37.7953" Top="506.45702" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="肝损伤/ / 肝脏负荷加重"/>
    <TfrxMemoView Name="Memo113" Left="37.7953" Top="532.91373" Width="646.29963" Height="41.57483" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="提示的肝损伤，并不完全等同于临床的肝功能异常。多因药物、酒精、内分泌或病毒引起、肝功能的临床&#13;&#10;指标可在正常范围内或临界。"/>
    <TfrxMemoView Name="Memo114" Left="37.7953" Top="574.48856" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="肝区代谢异常"/>
    <TfrxMemoView Name="Memo115" Left="37.7953" Top="600.94527" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="肝血管瘤、肝囊肿或肝脏生大疾病等可在肾区出现代谢热异常。"/>
    <TfrxMemoView Name="Memo116" Left="37.7953" Top="627.40198" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="腰骶椎损伤"/>
    <TfrxMemoView Name="Memo117" Left="37.7953" Top="653.85869" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="长期坐姿不良、外伤、高热史、缺钙、腰骶椎病变等均可导致腰骶椎不同程度的损伤。"/>
    <TfrxMemoView Name="Memo118" Left="37.7953" Top="680.3154" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="甲状腺代谢异常"/>
    <TfrxMemoView Name="Memo119" Left="37.7953" Top="706.77211" Width="646.29963" Height="37.7953" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="内分泌失调及甲状腺疾病均可导致甲状腺细胞代谢出现不同程度的异常。个别早期功能性改变临床检查可&#13;&#10;无具体体现。"/>
    <TfrxMemoView Name="Memo120" Left="37.7953" Top="744.56741" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="心动力不足"/>
    <TfrxMemoView Name="Memo121" Left="37.7953" Top="771.02412" Width="646.29963" Height="37.7953" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="提示的心动力不足，多是由于血液中脂肪含量过高，引起血液质量下降，从而导致心脏泵血能力降低所致，&#13;&#10;并不完全等同于心脏器质性病症。多伴有不同程度的脂肪肝。"/>
    <TfrxMemoView Name="Memo122" Left="37.7953" Top="808.81942" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="听力损伤"/>
    <TfrxMemoView Name="Memo123" Left="37.7953" Top="835.27613" Width="646.29963" Height="22.67718" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="多为手机辐射导致的听力损伤"/>
    <TfrxMemoView Name="Memo124" Left="37.7953" Top="857.95331" Width="646.29963" Height="26.45671" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="1" ParentFont="False" Text="肺部代谢异常"/>
    <TfrxMemoView Name="Memo125" Left="37.7953" Top="884.41002" Width="646.29963" Height="45.35436" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="肺部不同程度感染（包括细菌、病毒、结核等感染）、肺功能的异常或肺部重大疾病等可导致肺部代谢异&#13;&#10;常，个别早期功能性改变临床检查可无具体体现。"/>
    <TfrxPageHeader Name="PageHeader4" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="22.67718" Left="0" Top="18.89765" Width="718.1107">
      <TfrxMemoView Name="Memo22" Left="416.70099" Top="1" Width="298.63018" Height="18.89765" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" HAlign="haRight" ParentFont="False" Text="[exam.&#34;单位名称&#34;]">
        <Formats>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxMemoView Name="Memo68" Left="4.77953" Top="1" Width="447.30736" Height="18.89765" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="[person.&#34;患者名称&#34;]　[person.&#34;性别&#34;]　[person.&#34;年龄&#34;]     [exam.&#34;createdate&#34;]　">
        <Formats>
          <item/>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxLineView Name="Line4" Left="1" Top="20.84251969" Width="714.33117" Height="0" Color="8421504" Frame.Typ="4"/>
    </TfrxPageHeader>
  </TfrxReportPage>
  <TfrxReportPage Name="Page5" PaperWidth="210" PaperHeight="297" PaperSize="9" LeftMargin="10" RightMargin="10" TopMargin="10" BottomMargin="10" ColumnWidth="0" ColumnPositions.Text="" HGuides.Text="" VGuides.Text="">
    <TfrxMemoView Name="Memo130" Left="71.81107" Top="75.5906" Width="570.70903" Height="34.01577" Font.Charset="1" Font.Color="0" Font.Height="-19" Font.Name="Arial" Font.Style="1" HAlign="haCenter" ParentFont="False" Text="红外检测解读须知"/>
    <TfrxMemoView Name="Memo131" Left="34.01577" Top="132.28355" Width="646.29963" Height="321.26005" Font.Charset="1" Font.Color="0" Font.Height="-13" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="              医用红外热成像技术的特点在于它的高敏感度、高特异性、可以早期发现疾病、实时疗效监测、快速&#13;&#10;全面，并且对人体绝无任何辐射及伤害，孕妇、哺乳期妇女、儿童、老人均可进行检查。&#13;&#10;&#13;&#10;              疾病的变化必然有细胞代谢的变化与之对应。在疾病的早期，异常细胞代谢物的累积还未形成明显形&#13;&#10;态变化时，运用 CT、B 超是看不见的，但细胞代谢热的变化是从一开始就发生的，并不断从病变部位向体&#13;&#10;表传递。医用红外健康评估正是通过对全身的检查，而获取最全面准确的信息，对全身状况进行综合评估。&#13;&#10;&#13;&#10;              需要提醒您的是，医用红外发现的异常大多早于临床的疾病状态，故医用红外健康评估结果并不完全&#13;&#10;与临床同步，或等同于临床结果。"/>
    <TfrxPageHeader Name="PageHeader5" FillType="ftBrush" FillGap.Top="0" FillGap.Left="0" FillGap.Bottom="0" FillGap.Right="0" Height="22.67718" Left="0" Top="18.89765" Width="718.1107">
      <TfrxMemoView Name="Memo72" Left="413.03958" Top="1" Width="302.29159" Height="18.89765" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" HAlign="haRight" ParentFont="False" Text="[exam.&#34;单位名称&#34;]"/>
      <TfrxMemoView Name="Memo73" Left="4.77953" Top="1" Width="434.64595" Height="18.89765" DataSet="frxDBDataset_person" DataSetName="person" Font.Charset="1" Font.Color="0" Font.Height="-12" Font.Name="Arial" Font.Style="0" ParentFont="False" Text="[person.&#34;患者名称&#34;]　[person.&#34;性别&#34;]　[person.&#34;年龄&#34;]     [exam.&#34;createdate&#34;]　">
        <Formats>
          <item/>
          <item/>
          <item/>
        </Formats>
      </TfrxMemoView>
      <TfrxLineView Name="Line8" Left="1" Top="20.84251969" Width="714.33117" Height="0" Color="8421504" Frame.Typ="4"/>
    </TfrxPageHeader>
  </TfrxReportPage>
</TfrxReport>
