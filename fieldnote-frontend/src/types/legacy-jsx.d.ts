// react-day-picker 8 exposes React 17-style global JSX names while this
// generated frontend uses React 19 types. Keep the compatibility bridge local
// and explicit instead of suppressing declaration diagnostics globally.
import type * as React from "react";

declare global {
  namespace JSX {
    type Element = React.ReactElement;
    interface ElementClass extends React.Component<object> {}
    interface ElementAttributesProperty { props: {}; }
    interface ElementChildrenAttribute { children: {}; }
    interface IntrinsicAttributes extends React.Attributes {}
    interface IntrinsicClassAttributes<T> extends React.ClassAttributes<T> {}
    interface IntrinsicElements extends React.JSX.IntrinsicElements {}
  }
}

export {};
