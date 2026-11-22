export const auditViewTemplate = `
<section class="panel">
  <h2>审计争用</h2>
  <p class="hint">写动作落审计；后到争用只记 contention，不写业务。入金冲正与冲正偏航在下方专面可溯。</p>
  <div class="grid-2">
    <div>
      <h3>审计</h3>
      <table>
        <thead><tr><th>时间</th><th>人</th><th>动作</th><th>目标</th><th>载荷</th></tr></thead>
        <tbody>
          <tr v-for="a in audits" :key="a.id">
            <td>{{ a.created_at }}</td>
            <td>{{ a.actor }}</td>
            <td>
              {{ a.action }}
              <span v-if="a.action==='deposit_reversal'" class="badge done">冲正</span>
              <span v-if="a.action==='deposit_reversal_deviation'" class="badge fail">偏航</span>
            </td>
            <td>{{ a.target }}</td>
            <td><code style="font-size:11px">{{ a.payload }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div>
      <h3>入金冲正专面</h3>
      <p class="hint">
        锁死口径：{{ reversalPolicy.locked_label || '甲路径·同事务回滚' }}
        ｜偏航拒写 <span class="badge fail">{{ reversalAudit.deviation_count || 0 }}</span> 笔
      </p>
      <table>
        <thead><tr><th>冲正号</th><th>当事人</th><th>入金ID</th><th>金额</th><th>口径</th><th>状态</th><th>人</th></tr></thead>
        <tbody>
          <tr v-for="r in (reversalAudit.reversals||[])" :key="r.id">
            <td>{{ r.reversal_ref }}</td>
            <td>{{ r.party_key }}</td>
            <td>{{ r.deposit_id }}</td>
            <td class="amt-neg">{{ fmt(r.amount) }}</td>
            <td>{{ r.path_mode }}</td>
            <td>{{ r.status }}</td>
            <td>{{ r.actor }}</td>
          </tr>
        </tbody>
      </table>
      <p class="hint" v-if="!(reversalAudit.reversals||[]).length">暂无冲正流水。</p>
      <h3 style="margin-top:14px">持锁</h3>
      <table>
        <thead><tr><th>键</th><th>持有者</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="l in locks" :key="l.lock_key">
            <td>{{ l.lock_key }}</td>
            <td>{{ l.holder }}</td>
            <td>{{ l.acquired_at }}</td>
          </tr>
        </tbody>
      </table>
      <h3 style="margin-top:14px">争用</h3>
      <table>
        <thead><tr><th>时间</th><th>键</th><th>人</th><th>动作</th><th>详情</th></tr></thead>
        <tbody>
          <tr v-for="c in contention" :key="c.id">
            <td>{{ c.created_at }}</td>
            <td>{{ c.lock_key }}</td>
            <td>{{ c.actor }}</td>
            <td>{{ c.action }}</td>
            <td>{{ c.detail }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</section>
`;
