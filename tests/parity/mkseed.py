"""Builds seed.json (backup format) from base_backup.json — same data goes into the reference app and into 360."""
import json, datetime as dt, sys
import os
S=os.environ.get('PARITY_DIR','/tmp/anupam-parity')
base=json.load(open(f'{S}/base_backup.json'))
today=dt.date(2026,11,2)
def d(n): return (today+dt.timedelta(days=n)).isoformat()
def ts(n,h=10): return dt.datetime(2026,11,2,h,0,0).__add__(dt.timedelta(days=n)).isoformat()+'.000Z'
ch,bg=base['branches'][0],base['branches'][1]
base['branches']=[
 dict(ch, companyName='Anupam Bearings', address='12 Mount Road, Chennai 600002', gstNumber='33ABCDE1234F1Z5', phone='044 2345 6789', email='chennai@anupam.test'),
 dict(bg, companyName='Anupam Bearings (Bengaluru)', address='45 Peenya Industrial Area, Bengaluru 560058', gstNumber='29ABCDE1234F1Z5', phone='080 2345 6789', email='blr@anupam.test')]
E=lambda i,uid,name,role,brs: dict(id=f'emp{i}',userId=uid,name=name,password='secret1',role=role,branches=brs,phone=f'98400000{i:02d}',email=f'{uid}@anupam.test',empCode=f'AB-0{i}',workStart='09:30',workEnd='18:30',weeklyOff='0',active=True)
base['employees']=[E(1,'admin','Admin User','Admin',[ch['id'],bg['id']]),E(2,'manager','Manny Manager','Branch Manager',[ch['id']]),E(3,'staff','Sam Staff','Branch Staff',[ch['id']]),E(4,'sales','Sally Sales','Sales Manager',[ch['id']])]
base['salesPersons']=[dict(id='sp1',name='Ravi Kumar',phone='9811111111'),dict(id='sp2',name='Priya Nair',phone='9822222222')]
cust=[
 ('Sundaram Fasteners Ltd','Plant 3','Peenya Industrial Area','Bengaluru','Karnataka','560058','Conveyor Manufacturing','Referral','High',(13.0287,77.5197),'emp1'),
 ('Hindustan Gearbox Works','','Ambattur','Chennai','Tamil Nadu','600058','Gearbox Manufacturing','Cold Call','Medium',(13.1143,80.1548),'emp2'),
 ('Kovai Textile Machinery','Unit II','Avinashi Road','Coimbatore','Tamil Nadu','641018','Textile Machinery','Website','Low',(11.0168,76.9558),'emp3'),
 ('Deccan Agro Equipments','','Hebbal','Bengaluru','Karnataka','560024','Agricultural Machinery','Exhibition','High',None,'emp4'),
 ('Southern Packaging Pvt Ltd','','Guindy','Chennai','Tamil Nadu','600032','Packaging Machinery','LinkedIn','WhatsApp/Email Only',(13.0067,80.2206),'emp1'),
 ('Madurai Fan Industries','','SIPCOT','Madurai','Tamil Nadu','625016','Fan Manufacturing','Existing Customer','Medium',None,'emp2'),
]
cos=[];n=0
for i,(nm,pl,area,city,state,pin,ind,src,pot,geo,by) in enumerate(cust,1):
    cts=[]
    for j,(cn,jt) in enumerate([('Ravi Shankar','Purchase'),('Meena Iyer','Maintenance'),('Joseph D','GM')][: (3 if i%2 else 2)],1):
        ints=[]
        if i<=4:
            ints=[dict(id=f'int{i}{j}a',type='Call',date=d(-3*j-i),notes='Discussed bearing requirement for Q4',userId=by,createdAt=ts(-3*j-i),followupDate=d(4+j)),
                  dict(id=f'int{i}{j}b',type='Visit',date=d(-20-j),notes='Plant visit, met purchase team',userId=by,createdAt=ts(-20-j),location=dict(lat=geo[0],lng=geo[1]) if geo else None,alsoMet=[],jointWith=[])]
        cts.append(dict(id=f'ct{i}{j}',name=cn,jobTitle=jt,phone=f'9840{i}{j}0000'[:10],phone2='' if j>1 else f'9500{i}{j}1111'[:10],email=f'{cn.split()[0].lower()}{i}@example.com',dnd=(i==3 and j==2),interactions=ints))
    cos.append(dict(id=f'co{i}',name=nm,plant=pl,address=f'Plot {10+i}, {area}',area=area,city=city,state=state,pincode=pin,website=f'www.{nm.split()[0].lower()}.com',gstNumber=f'29ABCDE12{i}4F1Z5',
        plantGeo=dict(lat=geo[0],lng=geo[1],by=by,at=ts(-30)) if geo else None,
        hoName='Corporate Office' if i%3==0 else '',hoAddress='Nariman Point' if i%3==0 else '',hoCity='Mumbai' if i%3==0 else '',hoState='Maharashtra' if i%3==0 else '',hoPincode='400021' if i%3==0 else '',hoPhone='022 1234 5678' if i%3==0 else '',
        hoGeo=dict(lat=18.925,lng=72.82,by=by,at=ts(-30)) if i%3==0 else None,
        industry=ind,source=src,potential=pot,transportPreference='',courierPreference='',
        preferredLanguages=['English','Tamil'] if i%2 else ['Hindi'],interestedBrands=['Timken','SKF'] if i<4 else ['NSK'],interestedProducts=['Deep Groove Ball Bearing','Tapered Roller Bearing'],
        assignedTo=['Sam Staff'] if i in (1,3) else (['Sally Sales'] if i==4 else []),
        contacts=cts,createdById=by,createdAt=ts(-40+i)))
base['companies']=cos
def item(nm,q,r,dis=0,tax=18,unit='Nos'):
    amt=r*(1-dis/100); return dict(itemName=nm,make='Timken',qty=q,unit=unit,rate=r,discount=dis,tax=tax,amount=round(amt,2),value=round(amt*q,2))
docs=[]
def doc(i,typ,num,co,ct,branch,date,status,items,**kw):
    sub=sum(x['value'] for x in items); tot=round(sub*1.18,2)
    docs.append(dict(id=f'sd{i}',type=typ,docNumber=num,branch=branch,customerId=co,contactId=ct,date=date,status=status,orderStatus=status,items=items,subTotal=sub,totalAmount=tot,createdById='emp1',createdAt=ts(-10),packingCharges=0,freightCharges=0,otherCharges=0,roundOff=0,remarks='',salesPersonId='sp1',**{'callLog':[],**kw}))
doc(1,'enquiry','ENQ-0001','co1','ct11','Chennai',d(-12),'Pending',[item('6205 2RS Bearing',50,0,0,0)],source='Referral')
doc(2,'enquiry','ENQ-0002','co2','ct21','Chennai',d(-9),'Completed',[item('22212 E Spherical',10,0,0,0)],source='Cold Call')
doc(3,'quotation','QUO-0001','co1','ct11','Chennai',d(-8),'Pending',[item('6205 2RS Bearing',50,180,10),item('32008 Tapered',20,950,5)],validTill=d(7),refNo='RFQ-77',paymentTerms='Net 30 Days',callLog=[dict(id='cl1',message='Call not connecting',userId='emp1',timestamp=ts(-5))],terms=['Prices are exclusive of GST unless otherwise stated.'])
doc(4,'quotation','QUO-0002','co2','ct21','Chennai',d(-30),'Win',[item('NU 310',8,2400,0)],quotationValue=22656,validTill=d(-15))
doc(5,'quotation','QUO-0003','co3','ct31','Chennai',d(-35),'Lose',[item('51108 Thrust',30,320,0)],validTill=d(-20))
doc(6,'proforma','PI-0001','co1','ct11','Chennai',d(-6),'Pending',[item('6205 2RS Bearing',50,180,10)])
doc(7,'dc','DC-0001','co2','ct21','Chennai',d(-4),'Pending',[dict(item('NU 310',8,2400,0),supplyLog=[]),item('6308 ZZ',20,210,0)],vehicle='TN-09-AB-1234',transport='VRL Logistics')
doc(8,'po','PO-0001','co1','ct11','Chennai',d(-7),'Pending',[dict(item('6205 2RS Bearing',50,180,10),supplyLog=[dict(id='sl1',date=d(-3),qtySupplied=20,remarks='first lot',recordedById='emp1')])],refNo='PO-A-77')
base['salesDocs']=docs
base['docCounters']={}
base['payments']=[dict(id='pay1',customerId='co1',contactId='ct11',branch='Chennai',amount=50000,date=d(-10),remarks='Invoice INV-2045',createdById='emp1',createdAt=ts(-10),receivedLog=[dict(id='rc1',amount=20000,date=d(-5),mode='Cash',remarks='part',recordedById='emp1',createdAt=ts(-5))]),
                  dict(id='pay2',customerId='co2',contactId='ct21',branch='Chennai',amount=30000,date=d(-20),remarks='INV-2001',createdById='emp2',createdAt=ts(-20),receivedLog=[dict(id='rc2',amount=30000,date=d(-2),mode='Cash',remarks='',recordedById='emp2',createdAt=ts(-2))])]
base['tasks']=[
 dict(id='t1',title='Call Sundaram about quotation',description='Follow up QUO-0001',assignedToId='emp3',jointNames=[],priority='High',status='Open',taskType='Call',dueDate=d(0),relatedCustomerId='co1',relatedContactId='ct11',relatedDocId='sd3',createdById='emp1',createdAt=ts(-2)),
 dict(id='t2',title='Visit Hindustan Gearbox',description='',assignedToId='emp3',jointNames=['Manny Manager'],priority='Medium',status='Open',taskType='Visit',dueDate=d(2),relatedCustomerId='co2',createdById='emp2',createdAt=ts(-1)),
 dict(id='t3',title='Send catalogue',description='',assignedToId='emp1',jointNames=[],priority='Low',status='Done',taskType='',dueDate=d(-3),createdById='emp1',createdAt=ts(-6),completedAt=ts(-3)),
 dict(id='t4',title='Demo appointment at Kovai Textile',description='',assignedToId='emp4',jointNames=[],priority='Medium',status='Open',taskType='Appointment',dueDate=d(-1),relatedCustomerId='co3',createdById='emp1',createdAt=ts(-4))]
base['callAssignments']=[dict(id='ca1',customerId='co4',contactId='ct41',assignedToId='emp3',assignedById='emp2',weekOf='2026-11-02',status='Pending',remarks='',assignedAt=ts(-1),attempts=[]),
                         dict(id='ca2',customerId='co5',contactId='ct51',assignedToId='emp3',assignedById='emp2',weekOf='2026-11-02',status='Pending',remarks='',assignedAt=ts(-1),attempts=[dict(id='catt1',reason='Not Answered',note='',byId='emp3',at=ts(0))])]
base['notifications']=[dict(id='n1',userId='emp1',type='task_done',text='Sam Staff completed: Send catalogue',read=False,createdAt=ts(-1))]
base['approvals']=[]
base['attendance']=[dict(id=f'at{k}{u}',userId=f'emp{u}',date=d(-k),checkIn='09:3%d'%(k%9),checkOut='18:35',status='') for k in range(1,6) for u in (1,2,3)]
base['leaveRequests']=[dict(id='lv1',userId='emp3',from_=None,reason='Family function',status='Pending',requestedAt=ts(-1),**{'from':d(3),'to':d(4)})]
for l in base['leaveRequests']: l.pop('from_',None)
base['holidays']=[dict(id='h1',**{'from':d(10),'to':d(10)},name='Deepavali',all=True,branches=[])]
base['attendanceStart']=d(-30)
json.dump(base,open(f'{S}/seed.json','w'))
print('ok',len(cos),len(docs))
# denormalised names the reference stores alongside ids
cn={c['id']:c['name'] for c in base['companies']}; kn={k['id']:k['name'] for c in base['companies'] for k in c['contacts']}
for x in base['payments']+base['salesDocs']:
    x['customerName']=cn.get(x['customerId'],''); x['contactName']=kn.get(x.get('contactId'),'')
json.dump(base,open(f'{S}/seed.json','w'))
