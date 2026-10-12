const $ = (id) => document.getElementById(id);
let me = null;
let scanner = null;
let currentRecipients = [];

const pageMeta = {
  dashboard: ['Dashboard', 'Membership and access overview'], checkin: ['Member Check-in', 'Fast access control for the front desk'],
  members: ['Members', 'Register, search and manage gym members'], payments: ['Payments', 'Membership payments and revenue'],
  packages: ['Membership Packages', 'Manage membership products and prices'], emails: ['Email & Notices', 'Send reminders and notices to members'],
  staff: ['Staff Accounts', 'Manage staff access and roles'], activity: ['Activity Log', 'Review important staff actions'], reports: ['Reports', 'Download operational reports']
};

async function api(url, options = {}) {
  const response = await fetch(url, { credentials: 'same-origin', ...options });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { location.reload(); throw new Error('Authentication required'); }
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
}
function initials(name) { return String(name || 'M').split(/\s+/).map(x => x[0]).join('').slice(0,2).toUpperCase(); }
function money(v) { return '₦' + Number(v || 0).toLocaleString('en-NG', {maximumFractionDigits: 2}); }
function parseServerDate(v) {
  if (!v) return null;
  let s = String(v).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) s += 'T00:00:00';
  else if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(s)) s = s.replace(' ', 'T');
  let d = new Date(s);
  if (Number.isNaN(d.getTime())) {
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) d = new Date(Number(m[1]), Number(m[2])-1, Number(m[3]));
  }
  return Number.isNaN(d.getTime()) ? null : d;
}
function dateText(v) { const d=parseServerDate(v); return d ? d.toLocaleDateString('en-GB') : '-'; }
function dateTimeText(v) { const d=parseServerDate(v); return d ? d.toLocaleString('en-GB',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '-'; }

async function login(e) {
  e.preventDefault();
  $('loginError').classList.add('hidden');
  try {
    me = await api('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username:$('username').value.trim(), password:$('password').value})});
    showApp();
  } catch (err) { $('loginError').textContent = err.message; $('loginError').classList.remove('hidden'); }
}
async function showApp() {
  const who = await api('/api/me');
  me = who;
  $('loginPage').classList.add('hidden'); $('app').classList.remove('hidden');
  $('staffName').textContent = who.name; $('staffRole').textContent = who.role; $('staffAvatar').textContent = initials(who.name); $('topAvatar').textContent = initials(who.name);
  document.querySelectorAll('.nav-item[data-roles]').forEach(btn => {
    const roles = btn.dataset.roles.split(','); btn.classList.toggle('hidden', !roles.includes(who.role));
  });
  go('dashboard');
}
async function logout() { await api('/api/logout', {method:'POST'}).catch(()=>{}); location.reload(); }

function go(page) {
  if (!pageMeta[page]) page = 'dashboard';
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active-page'));
  $(page).classList.add('active-page');
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.page === page));
  $('pageTitle').textContent = pageMeta[page][0]; $('pageSubtitle').textContent = pageMeta[page][1];
  const loaders = {dashboard:loadDashboard, members:loadMembers, payments:loadPayments, packages:loadPackages, emails:loadEmails, staff:loadStaff, activity:loadActivity};
  if (loaders[page]) loaders[page]();
}

async function loadDashboard() {
  const d = await api('/api/dashboard');
  $('totalMembers').textContent = d.total; $('activeMembers').textContent = d.active; $('todayCount').textContent = d.today;
  $('monthlyRevenue').textContent = money(d.revenue); $('expiredMembers').textContent = d.expired; $('newMembers').textContent = d.new_month; $('renewalsMonth').textContent = d.renew_month; $('expiringSoon').textContent = d.expiring.length;
  $('recentCheckins').innerHTML = d.recent.length ? d.recent.map(x => `<div class="expiry"><div class="mini-avatar">${initials(x.full_name)}</div><div><b>${esc(x.full_name)}</b><small>${esc(x.member_id)} · ${new Date(x.checkin_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</small></div><span class="good">GRANTED</span></div>`).join('') : '<div class="empty">No check-ins yet.</div>';
  $('dashboardExpiring').innerHTML = d.expiring.length ? d.expiring.map(x => `<div class="expiry"><div class="mini-avatar">${initials(x.full_name)}</div><div><b>${esc(x.full_name)}</b><small>${esc(x.member_id)} · expires ${dateText(x.expiry_date)}</small></div><span class="danger-text">${x.days_left === 0 ? 'TODAY' : x.days_left + ' DAYS'}</span></div>`).join('') : '<div class="empty">No memberships expiring in the next 7 days.</div>';
}

async function checkAccess(code) {
  code = (code || $('memberId').value).trim(); if (!code) return;
  try {
    const d = await api('/api/checkin', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({code})});
    const r = $('accessResult'); r.className = 'panel result-panel ' + (d.granted ? 'granted' : 'denied');
    if (d.granted) r.innerHTML = `<div class="result-icon">✓</div><h2>ACCESS GRANTED</h2><p>Welcome, <b>${esc(d.member.full_name)}</b></p><p>${esc(d.member.member_id)} · ${esc(d.membership.package_name)} · Expires ${dateText(d.membership.expiry_date)}</p><small>${d.duplicate ? 'Already checked in today' : 'Check-in recorded'} · ${esc(d.checkin_time)}</small>`;
    else r.innerHTML = `<div class="result-icon">×</div><h2>ACCESS DENIED</h2><p><b>${esc(d.member?.full_name || '')}</b> — ${esc(d.reason)}</p>${d.membership?.expiry_date ? `<p>Expired: ${dateText(d.membership.expiry_date)}</p>` : ''}${d.reason === 'Membership expired' && d.member ? `<button class="primary" onclick="openRenew('${esc(d.member.member_id)}')">RENEW MEMBERSHIP</button>` : ''}`;
    $('memberId').value = '';
    loadDashboard();
  } catch (err) {
    const r = $('accessResult'); r.className = 'panel result-panel denied'; r.innerHTML = `<div class="result-icon">×</div><h2>ACCESS DENIED</h2><p>${esc(err.message)}</p>`;
  }
}

async function startScanner() {
  if (!window.Html5Qrcode) { alert('The camera scanner library could not load. Check the internet connection or use the Member ID box.'); return; }
  if (scanner) return;
  $('qr-reader').classList.remove('hidden'); $('stopScanner').classList.remove('hidden'); $('startScanner').classList.add('hidden');
  scanner = new Html5Qrcode('qr-reader');
  try {
    await scanner.start({facingMode:'environment'}, {fps:10, qrbox:{width:250,height:250}}, async text => {
      await checkAccess(text); await stopScanner();
    });
  } catch (e) { await stopScanner(); alert('Camera could not be started. Allow camera access and try again.'); }
}
async function stopScanner() {
  if (scanner) { try { await scanner.stop(); } catch(e) {} try { scanner.clear(); } catch(e) {} scanner = null; }
  $('qr-reader').classList.add('hidden'); $('stopScanner').classList.add('hidden'); $('startScanner').classList.remove('hidden');
}

async function loadMembers() {
  const d = await api('/api/members?q=' + encodeURIComponent($('memberSearch').value.trim()));
  $('membersTable').innerHTML = d.rows.length ? d.rows.map(m => `<tr><td><b>${esc(m.full_name)}</b><br><small>${esc(m.phone)}</small></td><td><b>${esc(m.member_id)}</b></td><td>${esc(m.email)}</td><td>${esc(m.package_name || '-')}</td><td>${dateText(m.expiry_date)}</td><td><span class="badge ${m.status === 'active' ? 'active-badge' : m.status === 'suspended' ? 'suspended-badge' : 'expired-badge'}">${esc(m.status)}</span></td><td><button class="action" onclick="openMember('${esc(m.member_id)}')">VIEW</button> <button class="action" onclick="openRenew('${esc(m.member_id)}')">RENEW</button> ${(me.role === 'Administrator') ? `<button class="action danger-action" onclick="archiveMember('${esc(m.member_id)}','${esc(m.full_name)}')">DELETE</button>` : ''}</td></tr>`).join('') : '<tr><td colspan="7" class="empty">No members found.</td></tr>';
}

async function openMember(id) {
  const d = await api('/api/members/' + encodeURIComponent(id)); const m=d.member;
  const managementButtons = (me.role === 'Administrator' || me.role === 'Manager') ? `<button class="secondary" onclick="editMember('${esc(m.member_id)}')">EDIT DETAILS</button><button class="secondary" onclick="openRenew('${esc(m.member_id)}')">RENEW</button><button class="secondary" onclick="changeStatus('${esc(m.member_id)}','${m.status === 'suspended' ? 'active' : 'suspended'}')">${m.status === 'suspended' ? 'REACTIVATE' : 'SUSPEND'}</button>${me.role === 'Administrator' ? `<button class="secondary danger-action" onclick="archiveMember('${esc(m.member_id)}','${esc(m.full_name)}')">DELETE MEMBER</button>` : ''}` : '';
  openModal(`<h2>${esc(m.full_name)}</h2><p class="muted">Member ${esc(m.member_id)} · ${esc(m.status)}</p><div class="profile-grid"><div><b>Phone</b><span>${esc(m.phone)}</span></div><div><b>Email</b><span>${esc(m.email)}</span></div><div><b>Package</b><span>${esc(d.membership?.package_name || '-')}</span></div><div><b>Expiry</b><span>${dateText(d.membership?.expiry_date)}</span></div></div><div class="qr-preview"><img src="/api/qr/${encodeURIComponent(m.member_id)}" alt="Member QR"><div><p><b>QR token:</b> ${esc(m.qr_code)}</p><button class="primary" onclick="sendQR('${esc(m.member_id)}')">EMAIL QR CODE</button></div></div><div class="modal-actions">${managementButtons}</div>`);
}
async function editMember(id) {
  const d=await api('/api/members/'+encodeURIComponent(id)); const m=d.member;
  openModal(`<h2>Edit Member</h2><p class="muted">${esc(m.member_id)}</p><div class="form-grid"><div><label>Full name</label><input id="editName" value="${esc(m.full_name)}"></div><div><label>Phone</label><input id="editPhone" value="${esc(m.phone)}"></div><div><label>Email</label><input id="editEmail" type="email" value="${esc(m.email)}"></div><div><label>Gender</label><select id="editGender"><option value="">Select</option><option ${m.gender==='Male'?'selected':''}>Male</option><option ${m.gender==='Female'?'selected':''}>Female</option></select></div><div><label>Emergency contact</label><input id="editEmergency" value="${esc(m.emergency_contact||'')}"></div></div><button class="primary full" onclick="saveMember('${esc(id)}')">SAVE DETAILS</button>`);
}
async function saveMember(id){try{await api('/api/members/'+encodeURIComponent(id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({full_name:$('editName').value,phone:$('editPhone').value,email:$('editEmail').value,gender:$('editGender').value,emergency_contact:$('editEmergency').value})});closeModal();loadMembers();}catch(e){alert(e.message)}}

async function sendQR(id) { try { await api('/api/members/'+encodeURIComponent(id)+'/send-qr',{method:'POST'}); alert('QR code emailed successfully.'); } catch(e) { alert(e.message); } }

async function openRenew(id) {
  const d = await api('/api/packages'); const m = await api('/api/members/'+encodeURIComponent(id));
  openModal(`<h2>Renew ${esc(m.member.full_name)}</h2><p class="muted">Choose the new package and payment details.</p><label>Package</label><select id="renewPackage">${d.rows.filter(p=>p.active).map(p=>`<option value="${p.id}" data-price="${p.price}">${esc(p.name)} — ${money(p.price)}</option>`).join('')}</select><label>Amount paid</label><input id="renewAmount" type="number"><label>Payment method</label><select id="renewMethod"><option>Cash</option><option>Bank Transfer</option><option>POS</option><option>Online Payment</option></select><label>Renewal start date</label><input id="renewStart" type="date" value="${new Date().toISOString().slice(0,10)}"><button class="primary full" onclick="submitRenew('${esc(id)}')">CONFIRM RENEWAL</button>`);
  $('renewPackage').addEventListener('change', () => $('renewAmount').value = $('renewPackage').selectedOptions[0].dataset.price); $('renewAmount').value = $('renewPackage').selectedOptions[0].dataset.price;
}
async function submitRenew(id) { try { await api('/api/members/'+encodeURIComponent(id)+'/renew',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({package_id:$('renewPackage').value,amount:$('renewAmount').value,payment_method:$('renewMethod').value,start_date:$('renewStart').value})}); closeModal(); alert('Membership renewed successfully.'); loadMembers(); loadDashboard(); } catch(e) { alert(e.message); } }
async function changeStatus(id,status) { try { await api('/api/members/'+encodeURIComponent(id)+'/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})}); closeModal(); loadMembers(); } catch(e){alert(e.message);} }

async function openAddMember() {
  const d = await api('/api/packages');
  openModal(`<h2>Register New Member</h2><p class="muted">The system will assign the next serial ID automatically (001, 002, 003…). You may enter a manual ID if authorised.</p><form id="newMemberForm"><div class="form-grid"><div><label>Full name *</label><input id="newName" required></div><div><label>Phone *</label><input id="newPhone" required></div><div><label>Email * <small>QR code will be sent here</small></label><input id="newEmail" type="email" required></div><div><label>Manual ID <small>optional</small></label><input id="newManualId" placeholder="Leave blank for next serial"></div><div><label>Gender</label><select id="newGender"><option value="">Select</option><option>Male</option><option>Female</option></select></div><div><label>Emergency contact</label><input id="newEmergency"></div><div><label>Package *</label><select id="newPackage">${d.rows.filter(p=>p.active).map(p=>`<option value="${p.id}" data-price="${p.price}">${esc(p.name)} — ${money(p.price)}</option>`).join('')}</select></div><div><label>Amount paid *</label><input id="newAmount" type="number" required></div><div><label>Start date *</label><input id="newStart" type="date" value="${new Date().toISOString().slice(0,10)}" required></div><div><label>Payment method *</label><select id="newMethod"><option>Cash</option><option>Bank Transfer</option><option>POS</option><option>Online Payment</option></select></div></div><button class="primary full" type="submit">REGISTER MEMBER & EMAIL QR</button><div id="registrationNotice" class="muted"></div></form>`);
  $('newPackage').addEventListener('change', () => $('newAmount').value = $('newPackage').selectedOptions[0].dataset.price); $('newAmount').value = $('newPackage').selectedOptions[0].dataset.price;
  $('newMemberForm').addEventListener('submit', submitMember);
}
async function submitMember(e) { e.preventDefault(); const btn=e.target.querySelector('button[type=submit]'); btn.disabled=true; btn.textContent='REGISTERING…'; try { const d=await api('/api/members',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({full_name:$('newName').value.trim(),phone:$('newPhone').value.trim(),email:$('newEmail').value.trim(),manual_member_id:$('newManualId').value.trim(),gender:$('newGender').value,emergency_contact:$('newEmergency').value.trim(),package_id:$('newPackage').value,amount:$('newAmount').value,payment_method:$('newMethod').value,start_date:$('newStart').value})}); $('registrationNotice').innerHTML=d.email_sent ? `<span class="good">Member ${esc(d.member_id)} registered and QR code emailed.</span>` : `<span class="danger-text">Member ${esc(d.member_id)} registered, but QR email failed: ${esc(d.email_error)}</span>`; setTimeout(()=>{closeModal();loadMembers();loadDashboard();},1200); } catch(err){alert(err.message);btn.disabled=false;btn.textContent='REGISTER MEMBER & EMAIL QR';} }

async function archiveMember(id,name){if(!confirm(`Remove ${name} (${id}) from active member management? This archives the member as inactive and preserves payment/attendance history.`))return;try{const d=await api('/api/members/'+encodeURIComponent(id)+'/delete',{method:'POST'});alert(d.message||'Member archived.');closeModal();await loadMembers();await loadDashboard();}catch(e){alert(e.message)}}

async function loadPayments(){ const d=await api('/api/payments'); const total=d.rows.reduce((s,x)=>s+Number(x.amount),0); $('paymentCount').textContent=d.rows.length; $('paymentRevenue').textContent=money(total); $('paymentsTable').innerHTML=d.rows.length?d.rows.map(p=>`<tr><td>${dateTimeText(p.payment_date)}</td><td><b>${esc(p.full_name)}</b><br><small>${esc(p.member_id)}</small></td><td>${esc(p.package_name)}</td><td>${esc(p.payment_type)}</td><td>${esc(p.payment_method)}</td><td><b>${money(p.amount)}</b></td><td>${esc(p.staff_name||'-')}</td></tr>`).join(''):'<tr><td colspan="7" class="empty">No payments.</td></tr>'; }

async function loadPackages(){ const d=await api('/api/packages'); $('packageGrid').innerHTML=d.rows.map(p=>`<div class="package ${p.active?'':'inactive-package'}"><span>${p.active?'ACTIVE':'INACTIVE'}</span><h2>${esc(p.name)}</h2><strong>${money(p.price)}</strong><p>${esc(p.description||'')}<br>${p.duration_days} day(s)</p><button class="secondary" onclick='editPackage(${JSON.stringify(p)})'>EDIT</button></div>`).join(''); }
function editPackage(p){ openModal(`<h2>Edit Package</h2><div class="form-grid"><div><label>Name</label><input id="pkgName" value="${esc(p.name)}"></div><div><label>Price</label><input id="pkgPrice" type="number" value="${p.price}"></div><div><label>Duration days</label><input id="pkgDays" type="number" value="${p.duration_days}"></div><div><label>Status</label><select id="pkgActive"><option value="1" ${p.active?'selected':''}>Active</option><option value="0" ${!p.active?'selected':''}>Inactive</option></select></div></div><label>Description</label><input id="pkgDesc" value="${esc(p.description||'')}"><button class="primary full" onclick="savePackage(${p.id})">SAVE PACKAGE</button>`); }
async function savePackage(id){try{await api('/api/packages/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('pkgName').value,price:$('pkgPrice').value,duration_days:$('pkgDays').value,description:$('pkgDesc').value,active:$('pkgActive').value==='1'})});closeModal();loadPackages();}catch(e){alert(e.message)}}
function addPackage(){openModal(`<h2>Add Package</h2><div class="form-grid"><div><label>Name</label><input id="pkgName"></div><div><label>Price</label><input id="pkgPrice" type="number"></div><div><label>Duration days</label><input id="pkgDays" type="number"></div></div><label>Description</label><input id="pkgDesc"><button class="primary full" onclick="createPackage()">CREATE PACKAGE</button>`)}
async function createPackage(){try{await api('/api/packages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('pkgName').value,price:$('pkgPrice').value,duration_days:$('pkgDays').value,description:$('pkgDesc').value})});closeModal();loadPackages();}catch(e){alert(e.message)}}

async function loadEmails(){ const cfg=await api('/api/email/config'); const msg=await api('/api/messages/config'); $('emailStatus').textContent=`Email ${cfg.configured?'ready':'not set'} · SMS ${msg.sms_configured?'ready':'not set'} · WhatsApp ${msg.whatsapp_configured?'ready':'not set'}`; $('emailStatus').className='status-pill '+((cfg.configured||msg.sms_configured||msg.whatsapp_configured)?'configured':'not-configured'); await loadRecipients(); await loadEmailHistory(); await loadMessageHistory(); updateMessageChannel(); }
async function loadRecipients(){ const d=await api('/api/email/recipients?filter='+encodeURIComponent($('recipientFilter').value)); currentRecipients=d.rows; $('recipientList').innerHTML=d.rows.length?d.rows.map(m=>`<label class="recipient"><input type="checkbox" class="recipient-check" value="${m.id}"><span><b>${esc(m.full_name)}</b><small>${esc(m.member_id)} · ${esc(m.phone||'No phone')} · ${esc(m.email||'No email')} · ${m.expiry_date?'expires '+dateText(m.expiry_date):'no expiry'}</small></span><em class="${m.status==='active'?'good':''}">${esc(m.status)}</em></label>`).join(''):'<div class="empty">No members match this filter.</div>'; updateSelectedCount(); }
function updateSelectedCount(){const n=document.querySelectorAll('.recipient-check:checked').length;$('selectedCount').textContent=n+' selected';}
function updateMessageChannel(){const ch=$('messageChannel').value; $('emailSubjectWrap').classList.toggle('hidden',ch!=='email'); $('sendBulkEmail').textContent=ch==='email'?'SEND EMAIL':ch==='sms'?'SEND SMS':'SEND WHATSAPP'; $('channelHelp').textContent=ch==='email'?'Email requires valid member email addresses.':ch==='sms'?'SMS uses Termii; provider charges may apply. Check phone numbers before sending.':'WhatsApp requires Meta WhatsApp Business Cloud API credentials. Outside the 24-hour customer-service window, use an approved template.';}
async function sendBulk(){const ids=[...document.querySelectorAll('.recipient-check:checked')].map(x=>Number(x.value));const channel=$('messageChannel').value;if(!ids.length)return alert('Select at least one member.');if(!$('emailBody').value.trim())return alert('Enter a message.');if(channel==='email'&&!$('emailSubject').value.trim())return alert('Enter an email subject.');if(!confirm(`Send ${channel.toUpperCase()} to ${ids.length} selected member(s)? Provider charges may apply.`))return;const b=$('sendBulkEmail');b.disabled=true;b.textContent='SENDING…';try{let d;if(channel==='email'){d=await api('/api/email/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_ids:ids,subject:$('emailSubject').value,body:$('emailBody').value,email_type:$('emailType').value})});}else{d=await api('/api/messages/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({member_ids:ids,channel,body:$('emailBody').value})});}$('emailResult').classList.remove('hidden');$('emailResult').textContent=`${channel.toUpperCase()} finished: ${d.sent} accepted, ${d.failed} failed.` + (d.results?.some(x=>x.status==='failed') ? ' Failed: '+d.results.filter(x=>x.status==='failed').map(x=>(x.phone||x.email||x.member_id)+': '+x.error).join(' | ') : '');await loadEmailHistory();await loadMessageHistory();}catch(e){alert(e.message)}finally{b.disabled=false;updateMessageChannel();}}
async function loadEmailHistory(){const d=await api('/api/email/log');$('emailHistoryTable').innerHTML=d.rows.length?d.rows.map(x=>`<tr><td>${dateTimeText(x.sent_at)}</td><td>${esc(x.recipient_email)}</td><td>${esc(x.member_id||'-')} ${x.full_name?'<small>'+esc(x.full_name)+'</small>':''}</td><td>${esc(x.email_type)}</td><td><span class="badge ${x.status==='sent'?'active-badge':'expired-badge'}">${esc(x.status)}</span></td><td>${esc(x.subject)}</td></tr>`).join(''):'<tr><td colspan="6" class="empty">No email history yet.</td></tr>';}

async function removeStaff(id,name){if(!confirm(`Remove staff account for ${name}? Their login will be disabled and past activity records preserved.`))return;try{const d=await api('/api/staff/'+id+'/delete',{method:'POST'});alert(d.message||'Staff account disabled.');await loadStaff();}catch(e){alert(e.message)}}
async function loadStaff(){const d=await api('/api/staff');$('staffTable').innerHTML=d.rows.map(s=>`<tr><td><b>${esc(s.full_name)}</b></td><td>${esc(s.username)}</td><td>${esc(s.email||'-')}</td><td>${esc(s.role)}</td><td>${esc(s.status)}</td><td>${dateTimeText(s.created_at)}</td><td><button class="action danger-action" onclick="removeStaff(${s.id},'${esc(s.full_name)}')">DELETE</button></td></tr>`).join('')||'<tr><td colspan="7" class="empty">No staff.</td></tr>';}
function addStaff(){openModal(`<h2>Add Staff Account</h2><div class="form-grid"><div><label>Full name</label><input id="staffFull"></div><div><label>Username</label><input id="staffUser"></div><div><label>Email</label><input id="staffEmail" type="email"></div><div><label>Password</label><input id="staffPass" type="password"></div><div><label>Role</label><select id="staffRoleInput"><option>Administrator</option><option>Manager</option><option>Receptionist</option></select></div></div><button class="primary full" onclick="createStaff()">CREATE STAFF</button>`)}
async function createStaff(){try{await api('/api/staff',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({full_name:$('staffFull').value,username:$('staffUser').value,email:$('staffEmail').value,password:$('staffPass').value,role:$('staffRoleInput').value})});closeModal();loadStaff();}catch(e){alert(e.message)}}
async function loadActivity(){const d=await api('/api/activity');$('activityTable').innerHTML=d.rows.map(x=>`<tr><td>${dateTimeText(x.created_at)}</td><td>${esc(x.staff_name||'-')}</td><td>${esc(x.action)}</td><td>${esc(x.details||'')}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No activity.</td></tr>';}

function changePassword(){openModal(`<h2>Change Password</h2><label>Current password</label><input id="currentPassword" type="password"><label>New password</label><input id="newPassword" type="password" placeholder="At least 8 characters"><button class="primary full" onclick="savePassword()">CHANGE PASSWORD</button>`)}
async function savePassword(){try{await api('/api/change-password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:$('currentPassword').value,new_password:$('newPassword').value})});closeModal();alert('Password changed successfully.');}catch(e){alert(e.message)}}

function openModal(html){$('modalContent').innerHTML=html;$('modal').classList.remove('hidden');}
function closeModal(){$('modal').classList.add('hidden');$('modalContent').innerHTML='';}

async function loadMessageHistory(){const d=await api('/api/messages/log');$('messageHistoryTable').innerHTML=d.rows.length?d.rows.map(x=>`<tr><td>${dateTimeText(x.sent_at)}</td><td>${esc(String(x.channel||'').toUpperCase())}</td><td>${esc(x.recipient)}</td><td>${esc(x.member_id||'-')} ${x.full_name?'<small>'+esc(x.full_name)+'</small>':''}</td><td><span class="badge ${x.status==='sent'?'active-badge':'expired-badge'}">${esc(x.status)}</span></td><td>${esc(x.error_message||x.provider_message_id||'-')}</td></tr>`).join(''):'<tr><td colspan="6" class="empty">No SMS or WhatsApp history yet.</td></tr>';}

$('loginForm').addEventListener('submit', login); $('logoutBtn').addEventListener('click', logout); $('changePasswordBtn').addEventListener('click', changePassword); $('checkAccessBtn').addEventListener('click',()=>checkAccess()); $('memberId').addEventListener('keydown',e=>{if(e.key==='Enter')checkAccess()}); $('startScanner').addEventListener('click',startScanner); $('stopScanner').addEventListener('click',stopScanner); $('addMemberBtn').addEventListener('click',openAddMember); $('memberSearch').addEventListener('input',()=>loadMembers()); $('closeModal').addEventListener('click',closeModal); $('modal').addEventListener('click',e=>{if(e.target===$('modal'))closeModal()}); $('addPackageBtn').addEventListener('click',addPackage); $('addStaffBtn').addEventListener('click',addStaff); $('recipientFilter').addEventListener('change',loadRecipients); $('refreshRecipients').addEventListener('click',loadRecipients); $('selectAllRecipients').addEventListener('change',e=>{document.querySelectorAll('.recipient-check').forEach(x=>x.checked=e.target.checked);updateSelectedCount()}); $('recipientList').addEventListener('change',e=>{if(e.target.classList.contains('recipient-check'))updateSelectedCount()}); $('sendBulkEmail').addEventListener('click',sendBulk); $('messageChannel').addEventListener('change',updateMessageChannel);
document.addEventListener('click',e=>{const nav=e.target.closest('[data-goto]');if(nav)go(nav.dataset.goto);const n=e.target.closest('.nav-item');if(n&&!n.classList.contains('hidden'))go(n.dataset.page);});
setInterval(()=>{$('clock').textContent=new Date().toLocaleString('en-NG',{weekday:'short',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});},1000); $('clock').textContent=new Date().toLocaleString('en-NG');
(async()=>{try{const x=await api('/api/me');if(x.authenticated)showApp();}catch(e){}})();
