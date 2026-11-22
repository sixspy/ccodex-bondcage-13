export const bondsViewTemplate = `
<section class="panel">
  <h2>保证金户</h2>
  <p class="hint">开户入金后，可用额 = 余额 − 已冻结。入笼只动冻结，不解出系统。入金冲正走锁死甲路径：同事务写流水+扣余额+审计，扣后可用为负整笔回滚。</p>
  <div class="grid-2">
    <div>
      <h3>开户</h3>
      <div class="form-row">
        <div>
          <label>当事人键</label>
          <input v-model="bondForm.party_key" placeholder="P-NEW"/>
        </div>
        <div>
          <label>名称</label>
          <input v-model="bondForm.party_name" placeholder="新公司"/>
        </div>
        <div>
          <label>开户入金</label>
          <input type="number" v-model.number="bondForm.initial_deposit" min="0" step="1000"/>
        </div>
      </div>
      <div class="actions">
        <button @click="openBond">开户</button>
      </div>
      <h3>入金</h3>
      <div class="form-row">
        <div>
          <label>当事人键</label>
          <input v-model="depositForm.party_key" placeholder="P-WEST"/>
        </div>
        <div>
          <label>金额</label>
          <input type="number" v-model.number="depositForm.amount" min="1" step="1000"/>
        </div>
        <div>
          <label>备注</label>
          <input v-model="depositForm.memo"/>
        </div>
      </div>
      <div class="actions">
        <button class="ok" @click="deposit">入金</button>
        <button class="secondary" @click="loadBondDetail(depositForm.party_key)">查看明细</button>
      </div>
      <h3>入金冲正 <span class="badge frozen">{{ reversalPolicy.locked_label || '甲路径·同事务回滚' }}</span></h3>
      <p class="hint">口径当日锁死（{{ reversalPolicy.locked_date || '2026-11-22' }}）：{{ reversalPolicy.memo || '' }}。只扣虚高余额，冻结不动；超额/偏航一律拒写。</p>
      <div class="form-row">
        <div>
          <label>当事人键</label>
          <input v-model="reversalForm.party_key" placeholder="P-INC" list="party-list-rev"/>
          <datalist id="party-list-rev">
            <option v-for="b in bonds" :key="b.party_key" :value="b.party_key"/>
          </datalist>
        </div>
        <div>
          <label>入金流水ID</label>
          <input type="number" v-model.number="reversalForm.deposit_id" min="1"/>
        </div>
        <div>
          <label>冲正金额</label>
          <input type="number" v-model.number="reversalForm.amount" min="0.01" step="1000"/>
        </div>
        <div>
          <label>原因</label>
          <input v-model="reversalForm.reason" placeholder="入金金额记错"/>
        </div>
      </div>
      <div class="actions">
        <button class="danger" @click="reverseDeposit">提交冲正（甲路径）</button>
      </div>
    </div>
    <div>
      <h3>账户一览</h3>
      <table>
        <thead>
          <tr><th>键</th><th>名称</th><th>余额</th><th>冻结</th><th>可用</th><th>状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="b in bonds" :key="b.id" @click="loadBondDetail(b.party_key)" style="cursor:pointer">
            <td>{{ b.party_key }}</td>
            <td>{{ b.party_name }}</td>
            <td>{{ fmt(b.balance) }}</td>
            <td>{{ fmt(b.frozen) }}</td>
            <td>{{ fmt(b.balance - b.frozen) }}</td>
            <td><span class="badge frozen">{{ b.status }}</span></td>
          </tr>
        </tbody>
      </table>
      <div v-if="bondDetail" style="margin-top:12px">
        <h3>明细 · {{ bondDetail.account.party_key }}</h3>
        <p class="hint">
          入金流水 {{ bondDetail.deposits.length }} 条 · 冲正 {{ (bondDetail.reversals||[]).length }} 笔 · 关联笼 {{ bondDetail.cages.length }} 只
        </p>
        <table>
          <thead><tr><th>入金（负为冲正）</th><th>备注</th><th>时间</th><th>操作者</th></tr></thead>
          <tbody>
            <tr v-for="d in bondDetail.deposits" :key="d.id">
              <td :class="d.amount < 0 ? 'amt-neg' : ''">{{ fmt(d.amount) }}</td>
              <td>{{ d.memo }}</td>
              <td>{{ d.created_at }}</td>
              <td>{{ d.actor }}</td>
            </tr>
          </tbody>
        </table>
        <h3 style="margin-top:12px">冲正流水（deposit_reversals）</h3>
        <table v-if="(bondDetail.reversals||[]).length">
          <thead><tr><th>冲正号</th><th>关联入金ID</th><th>金额</th><th>口径</th><th>状态</th><th>原因</th><th>人</th></tr></thead>
          <tbody>
            <tr v-for="r in bondDetail.reversals" :key="r.id">
              <td>{{ r.reversal_ref }}</td>
              <td>{{ r.deposit_id }}</td>
              <td class="amt-neg">{{ fmt(r.amount) }}</td>
              <td><span class="badge done">{{ r.path_mode }}</span></td>
              <td>{{ r.status }}</td>
              <td>{{ r.reason }}</td>
              <td>{{ r.actor }}</td>
            </tr>
          </tbody>
        </table>
        <p class="hint" v-else>该当事人暂无冲正流水。</p>
      </div>
    </div>
  </div>
</section>
`;
