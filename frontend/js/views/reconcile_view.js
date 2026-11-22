export const reconcileViewTemplate = `
<section class="panel">
  <h2>对账互证</h2>
  <p class="hint">笼口径：可用 + 已拨付 + 已罚没 = 笼总额（同笼代）。当事人口径：账户冻结 = 活笼可用合计；净入金（入金−冲正）− 拨付 − 罚没 = 账户余额。</p>
  <div class="actions">
    <button @click="loadReconcile">刷新对账</button>
    <button class="secondary" @click="loadProof">当事人互证</button>
    <button class="secondary" @click="loadAccountReconcile">账户轧平（含冲正）</button>
  </div>
  <div class="form-row" style="max-width:360px">
    <div>
      <label>当事人键（互证 / 轧平）</label>
      <input v-model="proofParty" list="party-list-recon"/>
      <datalist id="party-list-recon">
        <option v-for="b in bonds" :key="b.party_key" :value="b.party_key"/>
      </datalist>
    </div>
  </div>
  <div v-if="recon.summary" class="hint">
    合计 {{ recon.summary.total }} · 平衡 {{ recon.summary.balanced }} · 失衡 {{ recon.summary.unbalanced }}
  </div>
  <table>
    <thead>
      <tr>
        <th>笼</th><th>代</th><th>状态</th><th>总额</th><th>可用</th>
        <th>拨付</th><th>罚没</th><th>合计</th><th>平衡</th><th>缺口</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="i in (recon.items||[])" :key="i.cage_id">
        <td>{{ i.cage_code }}</td>
        <td>{{ i.generation }}</td>
        <td>{{ i.status }}</td>
        <td>{{ fmt(i.amount) }}</td>
        <td>{{ fmt(i.available) }}</td>
        <td>{{ fmt(i.released) }}</td>
        <td>{{ fmt(i.forfeited) }}</td>
        <td>{{ fmt(i.accounted) }}</td>
        <td>
          <span class="badge" :class="i.balanced?'pass':'fail'">{{ i.balanced ? '是' : '否' }}</span>
        </td>
        <td>{{ fmt(i.gap) }}</td>
      </tr>
    </tbody>
  </table>
  <div v-if="accountRecon" style="margin-top:14px">
    <h3>账户轧平 · {{ accountRecon.party_key }}</h3>
    <div class="proof-box">
      <div>{{ accountRecon.proof.balance_formula }}</div>
      <div>毛入金 {{ fmt(accountRecon.gross_deposit) }} － 冲正 {{ fmt(accountRecon.reversed_total) }} ＝ 净入金 {{ fmt(accountRecon.net_deposit) }}</div>
      <div>净入金 {{ fmt(accountRecon.net_deposit) }} － 拨付 {{ fmt(accountRecon.released_total) }} － 罚没 {{ fmt(accountRecon.forfeited_total) }}
        ＝ {{ fmt(accountRecon.balance_identity_left) }} ；账面余额 {{ fmt(accountRecon.balance_identity_right) }}</div>
      <div>余额轧平：
        <span class="badge" :class="accountRecon.balance_identity_ok?'pass':'fail'">{{ accountRecon.balance_identity_ok ? '是' : '否' }}</span>
        ｜冻结匹配活笼：
        <span class="badge" :class="accountRecon.frozen_matches_live?'pass':'fail'">{{ accountRecon.frozen_matches_live ? '是' : '否' }}</span>
        ｜总判定：
        <span class="badge" :class="accountRecon.balanced?'pass':'fail'">{{ accountRecon.balanced ? '同源平衡' : '失衡' }}</span>
      </div>
      <div>当前可用 {{ fmt(accountRecon.available) }}（余额 {{ fmt(accountRecon.account.balance) }} － 冻结 {{ fmt(accountRecon.account_frozen) }}）</div>
    </div>
  </div>
  <div v-if="partyProof" style="margin-top:14px">
    <h3>当事人互证 · {{ partyProof.party_key }}</h3>
    <div class="proof-box">{{ JSON.stringify(partyProof.proof, null, 2) }}
账户冻结 {{ fmt(partyProof.account.frozen) }}
活笼可用 {{ fmt(partyProof.live_cage_available) }}
匹配 {{ partyProof.frozen_matches_live }}
毛入金 {{ fmt(partyProof.gross_deposit) }} ｜ 冲正合计 {{ fmt(partyProof.reversed_total) }} ｜ 净入金 {{ fmt(partyProof.net_deposit) }}
余额轧平 {{ partyProof.balance_identity_ok }}
拨付合计 {{ fmt(partyProof.released_total) }}
罚没合计 {{ fmt(partyProof.forfeited_total) }}</div>
  </div>
</section>
`;
