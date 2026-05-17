/**
 * React renderers for the Pawrrtal artifact catalog.
 *
 * @fileoverview Each renderer corresponds 1:1 to an entry in
 * {@link ./catalog}. Renderers receive `{ props, children }` from
 * json-render and stay deliberately small — styling lives in the global
 * artifact stylesheet, not inline.
 */

import type { BaseComponentProps } from '@json-render/react';
import type { ReactNode } from 'react';

const cls = (...names: (string | false | undefined | null)[]) => names.filter(Boolean).join(' ');

type RendererMap = {
	[name: string]: (
		// We accept loose props here because the runtime catalog is the source
		// of truth — json-render validates against the zod schemas before this
		// renderer ever runs. Using `any` lets us write tight per-component
		// destructuring without juggling generic type parameters.
		// biome-ignore lint/suspicious/noExplicitAny: see comment above
		props: BaseComponentProps<any>
	) => ReactNode;
};

// Explicit type: each renderer accepts BaseComponentProps<any> so `props` and
// `children` are available. The cast in ArtifactRenderer.tsx bridges this to
// Components<typeof artifactCatalog> at the defineRegistry call-site.
export const artifactComponents: RendererMap = {
	Page: ({ props, children }) => (
		<div className={cls('artifact-page', `theme-${props.accent ?? 'cat'}`)}>{children}</div>
	),

	Section: ({ props, children }) => (
		<section className="artifact-section">
			<h2>{props.title}</h2>
			{props.lede ? <p className="artifact-lede">{props.lede}</p> : null}
			<div className="artifact-section-body">{children}</div>
		</section>
	),

	Heading: ({ props }) => {
		const Tag = (props.level ?? 'h2') as 'h1' | 'h2' | 'h3';
		return <Tag className={`artifact-heading artifact-heading-${Tag}`}>{props.text}</Tag>;
	},

	Paragraph: ({ props }) => <p className="artifact-paragraph">{props.text}</p>,

	StatPill: ({ props }) => (
		<div className="artifact-pill">
			<span className="artifact-pill-num">{props.value}</span>
			<span className="artifact-pill-label">{props.label}</span>
		</div>
	),

	CardRow: ({ props }) => (
		<div className="artifact-cards">
			{props.cards.map((c: { icon: string; title: string; body: string }) => (
				<div className="artifact-card" key={`${c.icon}-${c.title}-${c.body}`}>
					<div className="artifact-card-icon">{c.icon}</div>
					<h3>{c.title}</h3>
					<p>{c.body}</p>
				</div>
			))}
		</div>
	),

	BeforeAfter: ({ props }) => (
		<div className="artifact-rename">
			<div className="artifact-name-card before">
				<div className="artifact-name-card-label">before</div>
				<div className="artifact-name-card-name">{props.before}</div>
			</div>
			<div className="artifact-rename-arrow">→</div>
			<div className="artifact-name-card after">
				<div className="artifact-name-card-label">after</div>
				<div className="artifact-name-card-name">{props.after}</div>
			</div>
		</div>
	),

	ColumnList: ({ props }) => (
		<div className={cls('artifact-col', `artifact-col-${props.kind}`)}>
			<h3 className="artifact-col-title">
				<span className={cls('artifact-tag', `artifact-tag-${props.kind}`)}>
					{props.kind}
				</span>{' '}
				{props.title}
			</h3>
			<ul>
				{props.items.map((it: string) => (
					<li key={it}>{it}</li>
				))}
			</ul>
		</div>
	),

	BucketList: ({ children }) => <div className="artifact-buckets">{children}</div>,

	Bucket: ({ props }) => (
		<div className="artifact-bucket">
			<div className="artifact-bucket-head">
				<div className="artifact-bucket-num">{props.index}</div>
				<h3 className="artifact-bucket-title">{props.title}</h3>
				{props.where ? <span className="artifact-bucket-where">{props.where}</span> : null}
			</div>
			<div className="artifact-bucket-body">{props.body}</div>
		</div>
	),

	RouteTable: ({ props }) => (
		<table className="artifact-routes">
			<thead>
				<tr>
					<th>{props.headerLeft}</th>
					<th>{props.headerRight}</th>
				</tr>
			</thead>
			<tbody>
				{props.rows.map((r: { from: string; to: string }) => (
					<tr key={`${r.from}-${r.to}`}>
						<td>
							<code>{r.from}</code>
						</td>
						<td>
							<code>{r.to}</code>
						</td>
					</tr>
				))}
			</tbody>
		</table>
	),

	RiskGrid: ({ props }) => (
		<div className="artifact-risks">
			{props.items.map((it: { kind: 'ok' | 'warn' | 'bad'; title: string; body: string }) => (
				<div
					className={cls('artifact-risk', `artifact-risk-${it.kind}`)}
					key={`${it.kind}-${it.title}-${it.body}`}
				>
					<h4>{it.title}</h4>
					<p>{it.body}</p>
				</div>
			))}
		</div>
	),

	Steps: ({ props }) => (
		<ol className="artifact-steps">
			{props.items.map((s: { body: string }) => (
				<li key={s.body}>{s.body}</li>
			))}
		</ol>
	),
};
